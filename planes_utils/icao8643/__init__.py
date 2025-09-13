from pathlib import Path
import sqlite3

from .database import create_table_if_not_exists, create_unique_index, insert_records
from .icao_json import load_json_file


def import_icao_8643(
    json_files_dir: Path = Path("./data/icao_8643_files/"), 
    database_path: Path = Path("./planes.sqlite3")
):
    """Main function to process all JSON files and load into database."""
    JSON_PATTERN = "*.json"  # Change this to match your JSON files

    # Connect to database
    conn = sqlite3.connect(database_path)
    cursor = conn.cursor()

    try:
        # Create table and index
        create_table_if_not_exists(cursor)
        create_unique_index(cursor)

        # Find all JSON files
        json_files = list(
            json_files_dir.glob(JSON_PATTERN)
        )

        if not json_files:
            print(f"No JSON files found matching pattern: {JSON_PATTERN}")
            return

        print(f"Found {len(json_files)} JSON files to process")

        total_inserted = 0
        total_skipped = 0
        total_processed = 0

        # Process each JSON file
        for json_file in json_files:
            print(f"\nProcessing: {json_file}")

            # Load JSON data
            records = load_json_file(json_file)
            if not records:
                continue

            # Insert records
            inserted, skipped = insert_records(cursor, records)

            total_inserted += inserted
            total_skipped += skipped
            total_processed += len(records)

            print(f"  Inserted: {inserted}, Skipped (duplicates): {skipped}")

        # Commit all changes
        conn.commit()

        # Final summary
        print(f"\n" + "=" * 50)
        print(f"SUMMARY")
        print(f"=" * 50)
        print(f"Files processed: {len(json_files)}")
        print(f"Total records processed: {total_processed}")
        print(f"Records inserted: {total_inserted}")
        print(f"Records skipped (duplicates): {total_skipped}")

        # Show final table count
        cursor.execute("SELECT COUNT(*) FROM icao_8643")
        final_count = cursor.fetchone()[0]
        print(f"Total records in database: {final_count}")

    except Exception as e:
        print(f"Error: {e}")
        conn.rollback()

    finally:
        conn.close()
