# Management of the SQlite database in which the plane information will be stored.
import sqlite3
from typing import Any, Dict, List

from .icao_json import prepare_record


def create_table_if_not_exists(cursor: sqlite3.Cursor) -> None:
    """Create the icao_8643 table if it doesn't exist."""
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS icao_8643 (
            id INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT,
            manufacturer_code TEXT NOT NULL,
            model_no TEXT NOT NULL,
            model_name TEXT,
            model_version TEXT,
            engine_count INTEGER NOT NULL,
            engine_type TEXT NOT NULL,
            aircraft_desc TEXT NOT NULL,
            description TEXT NOT NULL,
            wtc TEXT(1) NOT NULL,
            tdesig TEXT NOT NULL,
            wtg TEXT(1)
        )
    """)


def create_unique_index(cursor: sqlite3.Cursor) -> None:
    """Create a unique index to prevent duplicates based on tdesig since this is what Flights API use."""
    cursor.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS idx_icao_8643_unique 
        ON icao_8643 (tdesig)
    """)


def insert_records(cursor: sqlite3.Cursor, records: List[Dict[str, Any]]) -> tuple:
    """Insert records using INSERT OR IGNORE to handle duplicates."""

    insert_sql = """
        INSERT OR IGNORE INTO icao_8643 (
            manufacturer_code, model_no, model_name, model_version,
            engine_count, engine_type, aircraft_desc, description,
            wtc, tdesig, wtg
        ) VALUES (
            :manufacturer_code, :model_no, :model_name, :model_version,
            :engine_count, :engine_type, :aircraft_desc, :description,
            :wtc, :tdesig, :wtg
        )
    """

    inserted_count = 0
    skipped_count = 0

    for record in records:
        cleaned_record = prepare_record(record)

        # Insert the record
        cursor.execute(insert_sql, cleaned_record)

        # Check if the record was actually inserted
        if cursor.rowcount > 0:
            inserted_count += 1
        else:
            skipped_count += 1

    return inserted_count, skipped_count
