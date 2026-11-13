
import csv
import json
from collections import defaultdict
from datetime import datetime
from pathlib import Path

from .database import DB_PATH, connect, initialize_database
from .encryption import decrypt_text


REPORT_COLUMNS = {
    "batch_summary.csv": [
        "workflow_id", "batch_id", "total_leads",
        "yet_to_reach_out", "in_progress_telephony_failed",
        "in_progress_dialed", "completed",
    ],
    "daily_overview.csv": [
        "workflow_id", "date", "total_calls",
        "connected_calls", "connectivity_rate", "success_leads",
    ],
    "lead_report.csv": [
        "workflow_id", "external_ref", "batch_id", "phone_masked",
        "bucket", "total_calls", "connected_calls", "last_call_at",
        "current_disposition", "ever_success",
    ],
    "rejections.csv": [
        "workflow_id", "batch_id", "row_number", "reason",
    ],
}


def _timestamp(value):
    return datetime.fromisoformat(value)


def _write_csv(path, columns, rows):
    with path.open("w", encoding="utf-8-sig", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=columns)
        writer.writeheader()
        writer.writerows(rows)


def _bucket(calls):
    if not calls:
        return "yet_to_reach_out"

    if any(call["terminal"] for call in calls):
        return "completed"

    if all(call["failed"] for call in calls):
        return "in_progress_telephony_failed"

    return "in_progress_dialed"


def _mask_phone(encrypted_phone):
    phone = decrypt_text(encrypted_phone)
    if not phone:
        return ""
    return "+91******" + phone[-4:]


def _build_calls(connection):
    events = connection.execute(
        """
        SELECT
            e.event_id,
            e.workflow_id,
            e.lead_id,
            e.event_type,
            e.call_id,
            e.occurred_at,
            e.payload_json,
            e.ignored,
            d.label,
            d.is_terminal,
            d.is_success
        FROM events e
        LEFT JOIN dispositions d
          ON d.workflow_id = e.workflow_id
         AND d.code = lower(
             json_extract(e.payload_json, '$.disposition_code')
         )
        WHERE e.lead_id IS NOT NULL
          AND e.call_id IS NOT NULL
          AND e.ignored = 0
        ORDER BY e.occurred_at, e.event_id
        """
    ).fetchall()

    grouped = defaultdict(list)

    for event in events:
        grouped[
            (event["workflow_id"], event["lead_id"], event["call_id"])
        ].append(event)

    calls_by_lead = defaultdict(list)
    daily = defaultdict(lambda: {
        "total_calls": 0,
        "connected_calls": 0,
        "success_leads": set(),
    })

    for (workflow_id, lead_id, call_id), items in grouped.items():
        initiated = [
            item for item in items
            if item["event_type"] == "call.initiated"
        ]

        if not initiated:
            continue

        initiated_at = min(
            initiated, key=lambda item: _timestamp(item["occurred_at"])
        )["occurred_at"]

        connected = any(
            item["event_type"] == "call.connected"
            for item in items
        )

        failed = any(
            item["event_type"] == "call.telephony_failed"
            for item in items
        )

        overrides = [
            item for item in items
            if item["event_type"] == "disposition.override"
            and item["label"] is not None
        ]

        dispositions = [
            item for item in items
            if item["event_type"] == "disposition.set"
            and item["label"] is not None
        ]

        candidates = overrides if overrides else dispositions

        effective = (
            max(
                candidates,
                key=lambda item: (
                    _timestamp(item["occurred_at"]),
                    item["event_id"],
                ),
            )
            if candidates else None
        )

        call = {
            "call_id": call_id,
            "initiated_at": initiated_at,
            "connected": connected,
            "failed": failed,
            "disposition": effective["label"] if effective else None,
            "terminal": bool(effective["is_terminal"]) if effective else False,
            "success": bool(effective["is_success"]) if effective else False,
        }

        calls_by_lead[(workflow_id, lead_id)].append(call)

        day = _timestamp(initiated_at).date().isoformat()
        daily_key = (workflow_id, day)
        daily[daily_key]["total_calls"] += 1

        if connected:
            daily[daily_key]["connected_calls"] += 1

        if call["success"]:
            daily[daily_key]["success_leads"].add(lead_id)

    return calls_by_lead, daily


def generate_reports(
    out_dir="reports",
    db_path=DB_PATH,
):
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    initialize_database(db_path)

    with connect(db_path) as connection:
        calls_by_lead, daily = _build_calls(connection)

        leads = connection.execute(
            """
            SELECT *
            FROM leads
            ORDER BY workflow_id, COALESCE(external_ref, '')
            """
        ).fetchall()

        lead_rows = []
        batch_counts = defaultdict(lambda: defaultdict(int))

        for lead in leads:
            workflow_id = lead["workflow_id"]
            lead_id = lead["id"]
            calls = calls_by_lead.get((workflow_id, lead_id), [])

            bucket = _bucket(calls)
            batch_key = (workflow_id, lead["batch_id"])

            batch_counts[batch_key]["total_leads"] += 1
            batch_counts[batch_key][bucket] += 1

            ordered_calls = sorted(
                calls,
                key=lambda call: _timestamp(call["initiated_at"]),
            )

            calls_with_disposition = [
                call for call in ordered_calls
                if call["disposition"] is not None
            ]

            last_call_at = (
                max(
                    ordered_calls,
                    key=lambda call: _timestamp(call["initiated_at"]),
                )["initiated_at"]
                if ordered_calls else ""
            )

            current_disposition = (
                calls_with_disposition[-1]["disposition"]
                if calls_with_disposition else ""
            )

            lead_rows.append({
                "workflow_id": workflow_id,
                "external_ref": lead["external_ref"] or "",
                "batch_id": lead["batch_id"],
                "phone_masked": _mask_phone(lead["phone_encrypted"]),
                "bucket": bucket,
                "total_calls": len(calls),
                "connected_calls": sum(
                    call["connected"] for call in calls
                ),
                "last_call_at": last_call_at,
                "current_disposition": current_disposition,
                "ever_success": str(
                    any(call["success"] for call in calls)
                ).lower(),
            })

        batch_rows = []

        for (workflow_id, batch_id), counts in sorted(batch_counts.items()):
            batch_rows.append({
                "workflow_id": workflow_id,
                "batch_id": batch_id,
                "total_leads": counts["total_leads"],
                "yet_to_reach_out": counts["yet_to_reach_out"],
                "in_progress_telephony_failed":
                    counts["in_progress_telephony_failed"],
                "in_progress_dialed": counts["in_progress_dialed"],
                "completed": counts["completed"],
            })

        daily_rows = []

        for (workflow_id, day), counts in sorted(daily.items()):
            total = counts["total_calls"]
            connected = counts["connected_calls"]

            daily_rows.append({
                "workflow_id": workflow_id,
                "date": day,
                "total_calls": total,
                "connected_calls": connected,
                "connectivity_rate": f"{connected / total:.4f}",
                "success_leads": len(counts["success_leads"]),
            })

        rejection_rows = [
            dict(row)
            for row in connection.execute(
                """
                SELECT workflow_id, batch_id, row_number, reason
                FROM rejections
                ORDER BY workflow_id, batch_id, row_number
                """
            ).fetchall()
        ]

        quality = {
            "lead_rows_total": 0,
            "lead_rows_rejected": 0,
            "rejections_by_reason": {},
            "duplicate_lead_rows_merged": 0,
            "field_warnings": 0,
            "events_total": 0,
            "malformed_events": 0,
            "duplicate_events_dropped": 0,
            "orphan_events": 0,
            "unknown_disposition_events": 0,
        }

        counters = connection.execute(
            "SELECT counter_name, counter_value FROM quality_counters"
        ).fetchall()

        for row in counters:
            counter_name = row["counter_name"]
            counter_value = row["counter_value"]

            if counter_name.startswith("field_warning:"):
                quality["field_warnings"] += counter_value
            elif counter_name in quality:
                quality[counter_name] = counter_value

        quality["lead_rows_rejected"] = len(rejection_rows)

        rejection_counts = connection.execute(
            "SELECT reason, count FROM rejection_counts ORDER BY reason"
        ).fetchall()

        quality["rejections_by_reason"] = {
            row["reason"]: row["count"] for row in rejection_counts
        }

        quality["duplicate_lead_rows_merged"] = connection.execute(
            "SELECT COALESCE(SUM(duplicate_count), 0) FROM leads"
        ).fetchone()[0]

        # Count unlinked events currently retained in the ledger.
        quality["orphan_events"] = connection.execute(
            "SELECT COUNT(*) FROM events WHERE lead_id IS NULL"
        ).fetchone()[0]

    _write_csv(
        out_dir / "batch_summary.csv",
        REPORT_COLUMNS["batch_summary.csv"],
        batch_rows,
    )
    _write_csv(
        out_dir / "daily_overview.csv",
        REPORT_COLUMNS["daily_overview.csv"],
        daily_rows,
    )
    _write_csv(
        out_dir / "lead_report.csv",
        REPORT_COLUMNS["lead_report.csv"],
        lead_rows,
    )
    _write_csv(
        out_dir / "rejections.csv",
        REPORT_COLUMNS["rejections.csv"],
        rejection_rows,
    )

    with (out_dir / "data_quality.json").open(
        "w", encoding="utf-8"
    ) as file:
        json.dump(quality, file, indent=2, ensure_ascii=False)

    return {
        "output_directory": str(out_dir.resolve()),
        "files": [
            "batch_summary.csv",
            "daily_overview.csv",
            "lead_report.csv",
            "rejections.csv",
            "data_quality.json",
        ],
        "leads_reported": len(lead_rows),
        "calls_reported": sum(
            item["total_calls"] for item in daily_rows
        ),
    }
