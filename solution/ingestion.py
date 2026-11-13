
import csv
import hashlib
import json
import re
import sqlite3
from pathlib import Path

from .database import (
    DB_PATH,
    connect,
    increment_counter,
    increment_rejection,
    initialize_database,
)
from .encryption import encrypt_text, phone_lookup_hash
from .normalizers import (
    normalize_enum,
    normalize_phone,
    parse_date,
    parse_decimal,
)
from .events import reconcile_event_links


ROOT = Path(__file__).resolve().parent.parent
SCHEMA_DIR = ROOT / "assignment-a-data" / "schemas"


def normalize_header(value: str) -> str:
    """Normalize CSV headers for canonical name and alias matching."""
    return re.sub(r"[_\s]+", " ", str(value).strip().lower())


def load_workflow_schema(workflow_id: str) -> dict:
    """Load the authoritative schema for a workflow."""
    schema_path = SCHEMA_DIR / f"{workflow_id}.json"

    if not schema_path.is_file():
        raise ValueError(f"Unknown workflow schema: {workflow_id}")

    with schema_path.open("r", encoding="utf-8") as file:
        schema = json.load(file)

    if schema.get("workflow_id") != workflow_id:
        raise ValueError(f"Workflow ID mismatch: {workflow_id}")

    return schema


def build_header_mapping(headers: list[str], fields: list[dict]) -> dict:
    """Map CSV headers to canonical schema fields."""
    aliases = {}

    for field in fields:
        canonical = field["name"]
        aliases[normalize_header(canonical)] = canonical

        for alias in field.get("aliases", []):
            aliases[normalize_header(alias)] = canonical

    mapping = {}

    for header in headers:
        canonical = aliases.get(normalize_header(header))

        if canonical and canonical not in mapping.values():
            mapping[header] = canonical

    return mapping


def is_blank_row(row: dict) -> bool:
    """Check whether all cells in a CSV row are empty."""
    return not any(
        value is not None and str(value).strip()
        for value in row.values()
    )


def normalize_field(field: dict, raw_value):
    """
    Normalize one field according to its schema type.

    Returns:
        (normalized_value, error_code)
    """
    if raw_value is None:
        return None, None

    value = str(raw_value).strip()

    if not value:
        return None, None

    field_type = field["type"]

    if field_type == "string":
        return value, None

    if field_type == "phone":
        normalized = normalize_phone(value)

        if normalized is None:
            return None, "invalid_phone"

        return normalized, None

    if field_type == "date":
        normalized = parse_date(value)

        if normalized is None:
            return None, "invalid_date"

        return normalized.isoformat(), None

    if field_type == "decimal":
        normalized = parse_decimal(value)

        if normalized is None:
            return None, "invalid_decimal"

        return format(normalized, ".2f"), None

    if field_type == "enum":
        normalized = normalize_enum(
            value,
            field.get("values", []),
        )

        if normalized is None:
            return None, "invalid_enum"

        return normalized, None

    raise ValueError(f"Unsupported field type: {field_type}")


def validate_lead_row(row: dict, mapping: dict, fields: list[dict]):
    """Validate and normalize a lead row in schema order."""
    raw_by_field = {}

    for header, canonical in mapping.items():
        raw_by_field[canonical] = row.get(header)

    normalized = {}
    warnings = []

    for field in fields:
        name = field["name"]
        raw_value = raw_by_field.get(name)

        if raw_value is None or not str(raw_value).strip():
            normalized[name] = None

            if field.get("required", False):
                return None, f"missing_required:{name}", []

            continue

        value, error = normalize_field(field, raw_value)

        if error:
            if field.get("required", False):
                return None, error, []

            normalized[name] = None
            warnings.append(name)
        else:
            normalized[name] = value

    return normalized, None, warnings


def file_sha256(path: Path) -> str:
    """Calculate SHA-256 without loading the complete file into memory."""
    digest = hashlib.sha256()

    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)

    return digest.hexdigest()


def apply_schema_defaults(values: dict, fields: list[dict]) -> dict:
    """Fill null fields with schema defaults after lead merging."""
    result = dict(values)

    for field in fields:
        name = field["name"]
        if result.get(name) is None and field.get("default") is not None:
            result[name] = field["default"]

    return result


def merge_lead(
    connection: sqlite3.Connection,
    workflow_id: str,
    batch_id: str,
    normalized: dict,
    fields: list[dict],
) -> bool:
    """
    Insert a new lead or merge an existing lead.

    Leads are identified by workflow_id and deterministic phone hash.
    PII is encrypted before database storage.
    """
    canonical_phone = normalized["phone"]
    phone_hash = phone_lookup_hash(canonical_phone)

    customer_name = normalized["customer_name"]

    external_field = next(
        field["name"]
        for field in fields
        if field.get("reference", False)
    )

    external_ref = normalized.get(external_field)

    non_pii_fields = {
        field["name"]: normalized.get(field["name"])
        for field in fields
        if not field.get("pii", False)
        and field["name"] not in ("phone", external_field)
    }

    existing = connection.execute(
        """
        SELECT id, fields_json
        FROM leads
        WHERE workflow_id = ?
          AND phone_hash = ?
        """,
        (workflow_id, phone_hash),
    ).fetchone()

    if existing is None:
        connection.execute(
            """
            INSERT INTO leads (
                workflow_id,
                phone_hash,
                phone_encrypted,
                customer_name_encrypted,
                external_ref,
                batch_id,
                fields_json
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                workflow_id,
                phone_hash,
                encrypt_text(canonical_phone),
                encrypt_text(customer_name),
                external_ref,
                batch_id,
                json.dumps(
                    apply_schema_defaults(non_pii_fields, fields),
                    ensure_ascii=False,
                ),
            ),
        )

        return False

    current_fields = json.loads(
        existing["fields_json"] or "{}"
    )

    # Keep existing values when incoming values are null.
    for name, value in non_pii_fields.items():
        if value is not None:
            current_fields[name] = value

    current_fields = apply_schema_defaults(current_fields, fields)

    connection.execute(
        """
        UPDATE leads
        SET customer_name_encrypted = ?,
            external_ref = COALESCE(?, external_ref),
            fields_json = ?,
            duplicate_count = duplicate_count + 1,
            updated_at = CURRENT_TIMESTAMP
        WHERE id = ?
        """,
        (
            encrypt_text(customer_name),
            external_ref,
            json.dumps(
                current_fields,
                ensure_ascii=False,
            ),
            existing["id"],
        ),
    )

    increment_counter(
        connection,
        "duplicate_lead_rows_merged",
    )

    return True


def ingest_lead_file(
    connection: sqlite3.Connection,
    csv_path: Path,
    drop_root: Path,
) -> dict:
    """Ingest one workflow lead CSV file."""
    workflow_id = csv_path.parent.name
    batch_id = csv_path.stem

    schema = load_workflow_schema(workflow_id)
    fields = schema["fields"]

    relative_path = csv_path.resolve().relative_to(
        ROOT
    ).as_posix()

    digest = file_sha256(csv_path)

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
                f"Already-processed file has changed: {relative_path}. "
                "Use a fresh database for changed source data."
            )

        return {
            "file": relative_path,
            "status": "already_processed",
            "rows": 0,
            "rejected": 0,
            "merged": 0,
        }

    row_count = 0
    rejected_count = 0
    merged_count = 0

    with csv_path.open(
        "r",
        encoding="utf-8-sig",
        newline="",
    ) as file:

        reader = csv.DictReader(file)

        if not reader.fieldnames:
            raise ValueError(
                f"CSV has no header: {relative_path}"
            )

        mapping = build_header_mapping(
            reader.fieldnames,
            fields,
        )

        # Reject a file with no recognizable required columns.
        mapped_fields = set(mapping.values())

        missing_columns = [
            field["name"]
            for field in fields
            if field.get("required", False)
            and field["name"] not in mapped_fields
        ]

        if missing_columns:
            raise ValueError(
                f"Missing required CSV columns in {relative_path}: "
                f"{missing_columns}"
            )

        for row in reader:
            if is_blank_row(row):
                continue

            row_count += 1

            increment_counter(
                connection,
                "lead_rows_total",
            )

            normalized, rejection_reason, warnings = (
                validate_lead_row(
                    row,
                    mapping,
                    fields,
                )
            )

            if rejection_reason:
                rejected_count += 1

                increment_counter(
                    connection,
                    "lead_rows_rejected",
                )

                increment_rejection(
                    connection,
                    rejection_reason,
                )

                connection.execute(
                    """
                    INSERT INTO rejections (
                        workflow_id,
                        batch_id,
                        row_number,
                        reason
                    )
                    VALUES (?, ?, ?, ?)
                    """,
                    (
                        workflow_id,
                        batch_id,
                        row_count,
                        rejection_reason,
                    ),
                )

                continue

            for field_name in warnings:
                increment_counter(
                    connection,
                    f"field_warning:{field_name}",
                )

            was_merged = merge_lead(
                connection,
                workflow_id,
                batch_id,
                normalized,
                fields,
            )

            if was_merged:
                merged_count += 1

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
        "rows": row_count,
        "rejected": rejected_count,
        "merged": merged_count,
    }


def ingest_leads(
    drop_dir: str | Path,
    db_path: str | Path = DB_PATH,
) -> list[dict]:
    """
    Ingest all CSV lead files in a drop.

    Supports deterministic ordering, duplicate merging,
    idempotent processing and event-to-lead reconciliation.
    """
    drop_root = Path(drop_dir).resolve()

    if not drop_root.is_dir():
        raise FileNotFoundError(
            f"Drop directory does not exist: {drop_root}"
        )

    leads_root = drop_root / "leads"

    if not leads_root.is_dir():
        raise FileNotFoundError(
            f"Missing leads directory: {leads_root}"
        )

    initialize_database(db_path)

    csv_files = sorted(
        leads_root.rglob("*.csv"),
        key=lambda path: path.as_posix().lower(),
    )

    results = []

    with connect(db_path) as connection:

        for csv_path in csv_files:
            results.append(
                ingest_lead_file(
                    connection,
                    csv_path,
                    drop_root,
                )
            )

        # Important: link events that arrived before their leads.
        reconcile_event_links(connection)

    return results
