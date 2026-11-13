import sqlite3

from solution.database import (
    connect,
    initialize_database,
    increment_counter,
    increment_rejection,
)


def test_database_creates_required_tables(tmp_path):
    db_path = tmp_path / "test.db"

    initialize_database(db_path)

    with connect(db_path) as connection:
        rows = connection.execute(
            """
            SELECT name
            FROM sqlite_master
            WHERE type = 'table'
            """
        ).fetchall()

    table_names = {row["name"] for row in rows}

    assert {
        "leads",
        "events",
        "processed_files",
        "quality_counters",
        "rejection_counts",
        "rejections",
        "dispositions",
    }.issubset(table_names)


def test_quality_counter_increments(tmp_path):
    db_path = tmp_path / "test.db"
    initialize_database(db_path)

    with connect(db_path) as connection:
        increment_counter(connection, "events_total")
        increment_counter(connection, "events_total", 4)

        row = connection.execute(
            """
            SELECT counter_value
            FROM quality_counters
            WHERE counter_name = 'events_total'
            """
        ).fetchone()

    assert row["counter_value"] == 5


def test_rejection_counter_increments(tmp_path):
    db_path = tmp_path / "test.db"
    initialize_database(db_path)

    with connect(db_path) as connection:
        increment_rejection(connection, "invalid_phone")
        increment_rejection(connection, "invalid_phone")

        row = connection.execute(
            """
            SELECT count
            FROM rejection_counts
            WHERE reason = 'invalid_phone'
            """
        ).fetchone()

    assert row["count"] == 2


def test_duplicate_lead_identity_is_prevented(tmp_path):
    db_path = tmp_path / "test.db"
    initialize_database(db_path)

    with connect(db_path) as connection:
        values = (
            "motor_renewal",
            "test_hash",
            "encrypted_phone",
            "encrypted_name",
            "MOT/2026/100001",
            "batch_001",
            "{}",
        )

        connection.execute(
            """
            INSERT INTO leads (
                workflow_id, phone_hash, phone_encrypted,
                customer_name_encrypted, external_ref, batch_id,
                fields_json
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            values,
        )

        try:
            connection.execute(
                """
                INSERT INTO leads (
                    workflow_id, phone_hash, phone_encrypted,
                    customer_name_encrypted, external_ref, batch_id,
                    fields_json
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                values,
            )
            assert False, "Duplicate lead should not be inserted"
        except sqlite3.IntegrityError:
            pass
