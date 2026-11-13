import sqlite3
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
DB_PATH = ROOT / "solution" / "ledger.db"


SCHEMA = """
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS leads (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    workflow_id TEXT NOT NULL,
    phone_hash TEXT NOT NULL,
    phone_encrypted TEXT NOT NULL,
    customer_name_encrypted TEXT NOT NULL,
    external_ref TEXT,
    batch_id TEXT NOT NULL,
    fields_json TEXT NOT NULL DEFAULT '{}',
    duplicate_count INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(workflow_id, phone_hash)
);

CREATE INDEX IF NOT EXISTS idx_leads_workflow_batch
ON leads(workflow_id, batch_id);

CREATE INDEX IF NOT EXISTS idx_leads_external_ref
ON leads(workflow_id, external_ref);


CREATE TABLE IF NOT EXISTS events (
    event_id TEXT PRIMARY KEY,
    workflow_id TEXT NOT NULL,
    event_type TEXT NOT NULL,
    call_id TEXT,
    occurred_at TEXT NOT NULL,
    phone_hash TEXT,
    phone_encrypted TEXT,
    payload_json TEXT NOT NULL DEFAULT '{}',
    lead_id INTEGER,
    ignored INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(lead_id) REFERENCES leads(id)
);

CREATE INDEX IF NOT EXISTS idx_events_call
ON events(workflow_id, call_id);

CREATE INDEX IF NOT EXISTS idx_events_lead
ON events(lead_id);

CREATE INDEX IF NOT EXISTS idx_events_phone
ON events(workflow_id, phone_hash);

CREATE INDEX IF NOT EXISTS idx_events_type_time
ON events(event_type, occurred_at);


CREATE TABLE IF NOT EXISTS processed_files (
    file_path TEXT PRIMARY KEY,
    file_hash TEXT NOT NULL,
    processed_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);


CREATE TABLE IF NOT EXISTS quality_counters (
    counter_name TEXT PRIMARY KEY,
    counter_value INTEGER NOT NULL DEFAULT 0
);


CREATE TABLE IF NOT EXISTS rejection_counts (
    reason TEXT PRIMARY KEY,
    count INTEGER NOT NULL DEFAULT 0
);


CREATE TABLE IF NOT EXISTS rejections (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    workflow_id TEXT NOT NULL,
    batch_id TEXT NOT NULL,
    row_number INTEGER NOT NULL,
    reason TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_rejections_sort
ON rejections(workflow_id, batch_id, row_number);


CREATE TABLE IF NOT EXISTS dispositions (
    workflow_id TEXT NOT NULL,
    code TEXT NOT NULL,
    label TEXT NOT NULL,
    is_terminal INTEGER NOT NULL,
    is_success INTEGER NOT NULL,
    PRIMARY KEY(workflow_id, code)
);
"""


def connect(db_path: Path | str = DB_PATH) -> sqlite3.Connection:
    """Open a SQLite connection with foreign keys and row access enabled."""
    connection = sqlite3.connect(str(db_path))
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    connection.execute("PRAGMA journal_mode = WAL")
    connection.execute("PRAGMA busy_timeout = 5000")
    return connection


def initialize_database(db_path: Path | str = DB_PATH) -> None:
    """Create all database tables and indexes if they do not exist."""
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)

    with connect(db_path) as connection:
        connection.executescript(SCHEMA)


def increment_counter(
    connection: sqlite3.Connection,
    name: str,
    amount: int = 1,
) -> None:
    """Atomically increment a named data-quality counter."""
    connection.execute(
        """
        INSERT INTO quality_counters(counter_name, counter_value)
        VALUES (?, ?)
        ON CONFLICT(counter_name)
        DO UPDATE SET counter_value = counter_value + excluded.counter_value
        """,
        (name, amount),
    )


def increment_rejection(
    connection: sqlite3.Connection,
    reason: str,
) -> None:
    """Increment the count for a particular rejection reason."""
    connection.execute(
        """
        INSERT INTO rejection_counts(reason, count)
        VALUES (?, 1)
        ON CONFLICT(reason)
        DO UPDATE SET count = count + 1
        """,
        (reason,),
    )
