
import csv
import hashlib
import json
import sqlite3
from pathlib import Path

from .database import (
    DB_PATH,
    connect,
    increment_counter,
    initialize_database,
)
from .encryption import encrypt_text, phone_lookup_hash
from .normalizers import normalize_phone, parse_timestamp


ROOT = Path(__file__).resolve().parent.parent
DISPOSITIONS_PATH = (
    ROOT / "assignment-a-data" / "schemas" / "dispositions.csv"
)


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()

    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)

    return digest.hexdigest()


def load_dispositions(connection: sqlite3.Connection) -> None:
    if not DISPOSITIONS_PATH.is_file():
        raise FileNotFoundError(DISPOSITIONS_PATH)

    with DISPOSITIONS_PATH.open(
        "r", encoding="utf-8-sig", newline=""
    ) as file:
        reader = csv.DictReader(file)

        required = {
            "workflow_id",
            "code",
            "label",
            "is_terminal",
            "is_success",
        }

        if not reader.fieldnames or not required.issubset(
            reader.fieldnames
        ):
            raise ValueError("Invalid dispositions.csv header")

        for row in reader:
            workflow = (row["workflow_id"] or "").strip()
            code = (row["code"] or "").strip().lower()
            label = (row["label"] or "").strip()

            terminal = (row["is_terminal"] or "").strip().lower()
            success = (row["is_success"] or "").strip().lower()

            if not workflow or not code or not label:
                raise ValueError("Invalid disposition row")

            if terminal not in {"true", "false"}:
                raise ValueError(f"Invalid is_terminal: {code}")

            if success not in {"true", "false"}:
                raise ValueError(f"Invalid is_success: {code}")

            connection.execute(
                """
                INSERT INTO dispositions (
                    workflow_id, code, label, is_terminal, is_success
                )
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(workflow_id, code)
                DO UPDATE SET
                    label = excluded.label,
                    is_terminal = excluded.is_terminal,
                    is_success = excluded.is_success
                """,
                (
                    workflow,
                    code,
                    label,
                    int(terminal == "true"),
                    int(success == "true"),
                ),
            )


def get_disposition_code(event_type: str, payload: dict):
    if event_type not in {
        "disposition.set",
        "disposition.override",
    }:
        return None

    value = payload.get("disposition_code")

    if value is None:
        return None

    value = str(value).strip().lower()
    return value or None


def is_known_disposition(
    connection: sqlite3.Connection,
    workflow_id: str,
    code: str | None,
) -> bool:
    if not code:
        return False

    return connection.execute(
        """
        SELECT 1
        FROM dispositions
        WHERE workflow_id = ? AND code = ?
        """,
        (workflow_id, code),
    ).fetchone() is not None


def reconcile_event_links(connection: sqlite3.Connection) -> int:
    before = connection.execute(
        "SELECT COUNT(*) FROM events WHERE lead_id IS NOT NULL"
    ).fetchone()[0]

    # Link regular events using the normalized phone hash.
    connection.execute(
        """
        UPDATE events
        SET lead_id = (
            SELECT l.id
            FROM leads l
            WHERE l.workflow_id = events.workflow_id
              AND l.phone_hash = events.phone_hash
        )
        WHERE lead_id IS NULL
          AND phone_hash IS NOT NULL
          AND EXISTS (
              SELECT 1
              FROM leads l
              WHERE l.workflow_id = events.workflow_id
                AND l.phone_hash = events.phone_hash
          )
        """
    )

    # Link overrides through another event from the same call.
    connection.execute(
        """
        UPDATE events AS e
        SET lead_id = (
            SELECT linked.lead_id
            FROM events linked
            WHERE linked.workflow_id = e.workflow_id
              AND linked.call_id = e.call_id
              AND linked.lead_id IS NOT NULL
              AND linked.event_id != e.event_id
            ORDER BY linked.occurred_at, linked.event_id
            LIMIT 1
        )
        WHERE e.event_type = 'disposition.override'
          AND e.lead_id IS NULL
          AND e.call_id IS NOT NULL
        """
    )

    after = connection.execute(
        "SELECT COUNT(*) FROM events WHERE lead_id IS NOT NULL"
    ).fetchone()[0]

    return after - before


def ingest_event_file(
    connection: sqlite3.Connection,
    jsonl_path: Path,
) -> dict:
    relative_path = jsonl_path.resolve().relative_to(
        ROOT
    ).as_posix()

    digest = file_sha256(jsonl_path)

    processed = connection.execute(
        """
        SELECT file_hash
        FROM processed_files
        WHERE file_path = ?
        """,
        (relative_path,),
    ).fetchone()

    if processed:
        if processed["file_hash"] != digest:
            raise ValueError(
                f"Already-processed file changed: {relative_path}"
            )

        return {
            "file": relative_path,
            "status": "already_processed",
            "events": 0,
            "malformed": 0,
            "duplicates": 0,
            "unknown_dispositions": 0,
            "newly_linked": 0,
        }

    counts = {
        "events": 0,
        "malformed": 0,
        "duplicates": 0,
        "unknown_dispositions": 0,
    }

    with jsonl_path.open("r", encoding="utf-8") as file:
        for line in file:
            if not line.strip():
                continue

            counts["events"] += 1
            increment_counter(connection, "events_total")

            try:
                event = json.loads(line)

                if not isinstance(event, dict):
                    raise ValueError("Event must be an object")

                event_id = str(event.get("event_id") or "").strip()
                event_type = str(event.get("event_type") or "").strip()
                workflow_id = str(event.get("workflow_id") or "").strip()
                occurred_at = str(event.get("occurred_at") or "").strip()

                if not all([
                    event_id,
                    event_type,
                    workflow_id,
                    occurred_at,
                ]):
                    raise ValueError("Missing required event field")

                timestamp = parse_timestamp(occurred_at)

            except (json.JSONDecodeError, ValueError, TypeError,
                    OverflowError):
                counts["malformed"] += 1
                increment_counter(connection, "malformed_events")
                continue

            existing = connection.execute(
                "SELECT 1 FROM events WHERE event_id = ?",
                (event_id,),
            ).fetchone()

            if existing:
                counts["duplicates"] += 1
                increment_counter(
                    connection, "duplicate_events_dropped"
                )
                continue

            payload = event.get("payload", {})

            if not isinstance(payload, dict):
                payload = {}

            call_id = event.get("call_id")
            call_id = str(call_id).strip() if call_id is not None else None
            call_id = call_id or None

            raw_phone = event.get("phone")
            canonical_phone = (
                normalize_phone(raw_phone)
                if raw_phone is not None
                else None
            )

            phone_hash = (
                phone_lookup_hash(canonical_phone)
                if canonical_phone else None
            )

            phone_encrypted = (
                encrypt_text(canonical_phone)
                if canonical_phone else None
            )

            ignored = 0

            code = get_disposition_code(event_type, payload)

            if event_type in {
                "disposition.set",
                "disposition.override",
            }:
                if not is_known_disposition(
                    connection, workflow_id, code
                ):
                    ignored = 1
                    counts["unknown_dispositions"] += 1
                    increment_counter(
                        connection, "unknown_disposition_events"
                    )

            connection.execute(
                """
                INSERT INTO events (
                    event_id,
                    workflow_id,
                    event_type,
                    call_id,
                    occurred_at,
                    phone_hash,
                    phone_encrypted,
                    payload_json,
                    lead_id,
                    ignored
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, NULL, ?)
                """,
                (
                    event_id,
                    workflow_id,
                    event_type,
                    call_id,
                    timestamp.isoformat(),
                    phone_hash,
                    phone_encrypted,
                    json.dumps(payload, ensure_ascii=False),
                    ignored,
                ),
            )

    newly_linked = reconcile_event_links(connection)

    connection.execute(
        """
        INSERT INTO processed_files(file_path, file_hash)
        VALUES (?, ?)
        """,
        (relative_path, digest),
    )

    return {
        "file": relative_path,
        "status": "processed",
        **counts,
        "newly_linked": newly_linked,
    }


def ingest_events(
    drop_dir: str | Path,
    db_path: str | Path = DB_PATH,
) -> list[dict]:
    drop_root = Path(drop_dir).resolve()

    if not drop_root.is_dir():
        raise FileNotFoundError(drop_root)

    events_root = drop_root / "events"

    if not events_root.is_dir():
        raise FileNotFoundError(events_root)

    initialize_database(db_path)

    jsonl_files = sorted(
        events_root.rglob("*.jsonl"),
        key=lambda path: path.as_posix().lower(),
    )

    results = []

    with connect(db_path) as connection:
        load_dispositions(connection)

        for path in jsonl_files:
            results.append(
                ingest_event_file(connection, path)
            )

        reconcile_event_links(connection)

    return results
