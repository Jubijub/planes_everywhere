"""Flight data import module for FlightRadar24 API integration."""

from datetime import datetime, timedelta, timezone
import sqlite3
import time
from typing import List, Optional, Tuple

from fr24sdk.client import Client
from fr24sdk.exceptions import ApiError, Fr24SdkError, RateLimitError

from . import SubscriptionPlan
from .utils import (
    apply_rate_limit,
    handle_fr24_exceptions,
    print_summary,
    setup_rate_limiting,
    validate_api_key,
)


def create_flights_table(db_path: str) -> None:
    """Create the flights table if it doesn't exist.

    Args:
        db_path: Path to the SQLite database file
    """
    with sqlite3.connect(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS flights (
                fr24_id TEXT PRIMARY KEY,
                hex TEXT,
                first_seen TEXT,
                last_seen TEXT,
                flight TEXT,
                type TEXT,
                operating_as TEXT,
                orig_icao TEXT,
                orig_iata TEXT,
                datetime_takeoff TEXT,
                runway_takeoff TEXT,
                dest_icao TEXT,
                dest_iata TEXT,
                datetime_landed TEXT,
                runway_landed TEXT,
                flight_time REAL,
                actual_distance REAL,
                last_updated TEXT,
                requires_update BOOLEAN DEFAULT TRUE
            )
        """)

        conn.commit()


def _get_existing_flight_range(
    db_path: str, airports: List[str]
) -> Tuple[Optional[datetime], Optional[datetime]]:
    """Get the range of existing flights for the given airports.

    Args:
        db_path: Path to the SQLite database file
        airports: List of airport codes

    Returns:
        Tuple of (earliest_first_seen, latest_first_seen) or (None, None) if no flights
    """
    with sqlite3.connect(db_path) as conn:
        cursor = conn.cursor()

        # Create placeholders for airports
        airport_placeholders = ",".join(["?" for _ in airports])

        cursor.execute(
            f"""
            SELECT MIN(first_seen), MAX(first_seen)
            FROM flights 
            WHERE orig_icao IN ({airport_placeholders}) 
               OR orig_iata IN ({airport_placeholders})
               OR dest_icao IN ({airport_placeholders})
               OR dest_iata IN ({airport_placeholders})
        """,
            airports * 4,
        )

        result = cursor.fetchone()

        if result and result[0] and result[1]:
            # Parse ISO datetime strings
            earliest = datetime.fromisoformat(result[0].replace("Z", "+00:00")).replace(
                tzinfo=None
            )
            latest = datetime.fromisoformat(result[1].replace("Z", "+00:00")).replace(
                tzinfo=None
            )
            return earliest, latest

        return None, None


def _generate_time_windows(
    start_datetime: datetime,
    end_datetime: datetime,
    max_hours: int = 6,
) -> List[Tuple[datetime, datetime]]:
    """Generate time windows for API calls to respect response limits.

    Args:
        start_datetime: Start datetime
        end_datetime: End datetime
        max_hours: Maximum hours per window

    Returns:
        List of (start, end) datetime tuples
    """
    windows = []
    current_start = start_datetime
    window_delta = timedelta(hours=max_hours)

    while current_start < end_datetime:
        current_end = min(current_start + window_delta, end_datetime)
        windows.append((current_start, current_end))
        current_start = current_end

    return windows


@handle_fr24_exceptions("flight import")
def import_flights(
    airports: List[str],
    start_datetime: datetime,
    end_datetime: datetime,
    db_path: str,
    fr24_api_key: Optional[str] = None,
    plan: Optional[SubscriptionPlan] = None,
) -> Tuple[int, int]:
    """Import flights from/to specific airports between two datetimes.

    Args:
        airports: List of airport IATA/ICAO codes
        start_datetime: Start datetime for flight search (must be timezone-naive UTC)
        end_datetime: End datetime for flight search (must be timezone-naive UTC)
        db_path: Path to the SQLite database file
        fr24_api_key: Optional FR24 API key. If None, uses FR24_API_TOKEN from environment.
        plan: Optional subscription plan for rate limiting. If None, no rate limiting is applied.

    Returns:
        Tuple of (imported_count, ignored_count)

    Raises:
        ValueError: If FR24_API_TOKEN not found in environment and fr24_api_key is None
        RateLimitError: If FR24 API rate limit is exceeded
    """
    # Validate timezone-naive datetimes
    if start_datetime.tzinfo is not None or end_datetime.tzinfo is not None:
        raise ValueError("Datetimes must be timezone-naive (assumed UTC)")

    fr24_api_key = validate_api_key(fr24_api_key)

    # Create table if it doesn't exist
    create_flights_table(db_path)

    # Check existing data to optimize API calls
    earliest_existing, latest_existing = _get_existing_flight_range(db_path, airports)

    # Adjust time range to avoid redundant API calls
    actual_start = start_datetime
    actual_end = end_datetime

    if earliest_existing and latest_existing:
        # Check if requested range is completely covered by existing data
        if start_datetime >= earliest_existing and end_datetime <= latest_existing:
            # Entire requested range is already covered - no API calls needed
            print(f"All flights in range {start_datetime} to {end_datetime} already exist in database")
            return 0, 0
        
        # Handle partial overlaps - only fetch missing data
        if start_datetime < earliest_existing:
            if end_datetime <= earliest_existing:
                # Entire requested range is before existing data
                actual_end = earliest_existing
            # else: Will fetch before existing data, existing logic handles this
        elif start_datetime <= latest_existing:
            # Start is within existing range, only fetch after latest_existing
            if end_datetime > latest_existing:
                print(f"Data exists from {earliest_existing} to {latest_existing}, only fetching from {latest_existing} onwards")
                actual_start = latest_existing
            else:
                # Entire range is within existing data
                print(f"All flights in range {start_datetime} to {end_datetime} already exist in database")
                return 0, 0
        else:
            # start_datetime > latest_existing - entire range is after existing data
            actual_start = start_datetime

    # Generate time windows (max 6 hours each)
    time_windows = _generate_time_windows(actual_start, actual_end)

    # If we have existing data in the middle, we need to handle gaps
    if earliest_existing and latest_existing:
        if start_datetime < earliest_existing and end_datetime > latest_existing:
            # Need to get data before and after existing range
            before_windows = _generate_time_windows(start_datetime, earliest_existing)
            after_windows = _generate_time_windows(latest_existing, end_datetime)
            time_windows = before_windows + after_windows

    total_imported = 0
    total_ignored = 0
    total_fetched = 0
    all_ignored_ids = []

    # Setup rate limiting
    sleep_time = setup_rate_limiting(plan)

    with Client(api_token=fr24_api_key) as client:
        for i, (window_start, window_end) in enumerate(time_windows):
            print(f"Fetching flights from {window_start} to {window_end}")

            # Apply rate limiting
            apply_rate_limit(sleep_time, is_first_request=(i == 0))

            summary = client.flight_summary.get_full(
                airports=airports,
                flight_datetime_from=window_start,
                flight_datetime_to=window_end,
            )

            if not summary.data:
                continue

            total_fetched += len(summary.data)

            imported_count, ignored_count, ignored_ids = _insert_flights(
                db_path, summary.data
            )
            total_imported += imported_count
            total_ignored += ignored_count
            all_ignored_ids.extend(ignored_ids)

        # Print summary
        summary_data: dict[str, int | str] = {
            "flights_fetched_from_api": total_fetched,
            "flights_inserted": total_imported,
            "flights_ignored_duplicates": total_ignored,
        }
        if all_ignored_ids:
            summary_data["ignored_flight_ids"] = ", ".join(all_ignored_ids)

        print_summary("IMPORT FLIGHTS SUMMARY", **summary_data)
        return total_imported, total_ignored


def _insert_flights(db_path: str, flights) -> Tuple[int, int, List[str]]:
    """Insert flights into database, handling duplicates and missing ICAO types.

    Args:
        db_path: Path to the SQLite database file
        flights: List of flight data from FR24 API

    Returns:
        Tuple of (imported_count, ignored_count, ignored_flight_ids)
    """
    imported_count = 0
    ignored_count = 0
    ignored_flight_ids = []

    with sqlite3.connect(db_path) as conn:
        cursor = conn.cursor()

        for flight in flights:
            try:
                # Determine if flight requires future updates
                from datetime import datetime, timedelta, timezone

                # Parse first_seen to check if flight is >24h old
                first_seen_dt = datetime.fromisoformat(
                    flight.first_seen.replace("Z", "+00:00")
                )
                is_old_flight = (
                    datetime.now(timezone.utc) - first_seen_dt
                ) > timedelta(hours=24)

                # Flight has both takeoff and landing data
                has_complete_data = (
                    flight.datetime_takeoff is not None
                    and flight.datetime_landed is not None
                )

                # Only require updates for recent incomplete flights
                requires_update = not (is_old_flight or has_complete_data)

                cursor.execute(
                    """
                    INSERT INTO flights (
                        fr24_id, hex, first_seen, last_seen, flight, type,
                        operating_as, orig_icao, orig_iata, datetime_takeoff,
                        runway_takeoff, dest_icao, dest_iata, datetime_landed,
                        runway_landed, flight_time, actual_distance, last_updated, requires_update
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                    (
                        flight.fr24_id,
                        flight.hex.lower() if flight.hex else None,
                        flight.first_seen,
                        flight.last_seen,
                        flight.flight,
                        flight.type,
                        flight.operating_as,
                        flight.orig_icao,
                        flight.orig_iata,
                        flight.datetime_takeoff,
                        flight.runway_takeoff,
                        flight.dest_icao,
                        flight.dest_iata,
                        flight.datetime_landed,
                        flight.runway_landed,
                        flight.flight_time,
                        flight.actual_distance,
                        datetime.now(timezone.utc).isoformat(),
                        requires_update,
                    ),
                )

                imported_count += 1

            except sqlite3.IntegrityError:
                # Duplicate fr24_id (primary key violation)
                ignored_count += 1
                ignored_flight_ids.append(flight.fr24_id)
                continue
            except sqlite3.Error as e:
                print(f"Warning: Failed to insert flight {flight.fr24_id}: {e}")
                continue

        conn.commit()

    return imported_count, ignored_count, ignored_flight_ids


@handle_fr24_exceptions("flight update")
def update_flights(
    start_datetime: datetime,
    end_datetime: datetime,
    db_path: str,
    fr24_api_key: Optional[str] = None,
    plan: Optional[SubscriptionPlan] = None,
) -> Tuple[int, int]:
    """Update incomplete flights that are missing takeoff or landing information.

    Args:
        start_datetime: Start datetime for flight search (must be timezone-naive UTC)
        end_datetime: End datetime for flight search (must be timezone-naive UTC)
        db_path: Path to the SQLite database file
        fr24_api_key: Optional FR24 API key. If None, uses FR24_API_TOKEN from environment.
        plan: Optional subscription plan for rate limiting. If None, no rate limiting is applied.

    Returns:
        Tuple of (updated_count, not_found_count)

    Raises:
        ValueError: If FR24_API_TOKEN not found in environment and fr24_api_key is None
        RateLimitError: If FR24 API rate limit is exceeded
        ApiError: If FR24 API returns an error
        Fr24SdkError: If FR24 SDK encounters an error
    """
    # Validate timezone-naive datetimes
    if start_datetime.tzinfo is not None or end_datetime.tzinfo is not None:
        raise ValueError("Datetimes must be timezone-naive (assumed UTC)")

    fr24_api_key = validate_api_key(fr24_api_key)

    # Generate time windows (max 14 days each for update_flights)
    time_windows = _generate_time_windows(start_datetime, end_datetime)

    updated_count = 0
    not_found_count = 0
    total_fetched = 0
    all_found_flight_ids = set()
    all_incomplete_flight_ids = set()

    # Setup rate limiting
    sleep_time = setup_rate_limiting(plan)

    with Client(api_token=fr24_api_key) as client:
        for window_start, window_end in time_windows:
            print(f"Updating flights from {window_start} to {window_end}")

            # Get incomplete flights for this specific time window
            with sqlite3.connect(db_path) as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """
                    SELECT fr24_id
                    FROM flights 
                    WHERE requires_update = TRUE
                      AND first_seen >= ?
                      AND first_seen <= ?
                """,
                    (window_start.isoformat() + "Z", window_end.isoformat() + "Z"),
                )

                rows = cursor.fetchall()
                if not rows:
                    print(f"  No incomplete flights found for this time window")
                    continue

                window_incomplete_flight_ids = [row[0] for row in rows]
                all_incomplete_flight_ids.update(window_incomplete_flight_ids)

            print(
                f"  Found {len(window_incomplete_flight_ids)} incomplete flights in this window"
            )

            # Chunk flight IDs into batches of 15 (FR24 API limit)
            batch_size = 15
            for i in range(0, len(window_incomplete_flight_ids), batch_size):
                batch_ids = window_incomplete_flight_ids[i : i + batch_size]
                print(
                    f"  Processing batch {i // batch_size + 1}: {len(batch_ids)} flight IDs"
                )

                # Apply rate limiting (skip delay on first batch of first window)
                is_first_request = window_start == time_windows[0][0] and i == 0
                apply_rate_limit(sleep_time, is_first_request=is_first_request)

                summary = client.flight_summary.get_full(
                    flight_ids=batch_ids,
                    flight_datetime_from=window_start,
                    flight_datetime_to=window_end,
                )

                if not summary.data:
                    continue

                total_fetched += len(summary.data)

                # Update flights in database
                with sqlite3.connect(db_path) as conn:
                    cursor = conn.cursor()

                    for flight in summary.data:
                        all_found_flight_ids.add(flight.fr24_id)

                        # Check current flight data to see what was missing
                        cursor.execute(
                            "SELECT datetime_takeoff, datetime_landed FROM flights WHERE fr24_id = ?",
                            (flight.fr24_id,),
                        )
                        current_data = cursor.fetchone()

                        if current_data:
                            current_takeoff, current_landed = current_data

                            # Determine if this update provides new meaningful data
                            provides_takeoff = (
                                current_takeoff is None
                                and flight.datetime_takeoff is not None
                            )
                            provides_landing = (
                                current_landed is None
                                and flight.datetime_landed is not None
                            )

                            # Check if flight no longer requires updates after this update
                            has_complete_data_after_update = (
                                current_takeoff is not None
                                or flight.datetime_takeoff is not None
                            ) and (
                                current_landed is not None
                                or flight.datetime_landed is not None
                            )

                            # Parse first_seen to check if flight is >24h old
                            is_old_flight = False
                            if flight.first_seen:
                                first_seen_dt = datetime.fromisoformat(
                                    flight.first_seen.replace("Z", "+00:00")
                                )
                                is_old_flight = (
                                    datetime.now(timezone.utc) - first_seen_dt
                                ) > timedelta(hours=24)
                            
                            # Flight no longer requires updates if:
                            # 1. It now has complete data, OR
                            # 2. It's old (>24h) AND API didn't provide new data (give up on old flights)
                            should_stop_updating = (
                                has_complete_data_after_update
                                or (is_old_flight and not (provides_takeoff or provides_landing))
                            )

                            # Build base update values
                            update_values = [
                                flight.hex.lower() if flight.hex else None,
                                flight.first_seen,
                                flight.last_seen,
                                flight.flight,
                                flight.type,
                                flight.operating_as,
                                flight.orig_icao,
                                flight.orig_iata,
                                flight.datetime_takeoff,
                                flight.runway_takeoff,
                                flight.dest_icao,
                                flight.dest_iata,
                                flight.datetime_landed,
                                flight.runway_landed,
                                flight.flight_time,
                                flight.actual_distance,
                            ]

                            # Add update control fields if we should stop updating
                            if should_stop_updating:
                                update_sql = """
                                    UPDATE flights SET
                                        hex = ?, first_seen = ?, last_seen = ?, flight = ?, type = ?,
                                        operating_as = ?, orig_icao = ?, orig_iata = ?, datetime_takeoff = ?,
                                        runway_takeoff = ?, dest_icao = ?, dest_iata = ?, datetime_landed = ?,
                                        runway_landed = ?, flight_time = ?, actual_distance = ?,
                                        last_updated = ?, requires_update = ?
                                    WHERE fr24_id = ?
                                """
                                update_values.extend(
                                    [
                                        datetime.now(timezone.utc).isoformat(),
                                        False,  # Stop future updates
                                        flight.fr24_id,
                                    ]
                                )
                            else:
                                update_sql = """
                                    UPDATE flights SET
                                        hex = ?, first_seen = ?, last_seen = ?, flight = ?, type = ?,
                                        operating_as = ?, orig_icao = ?, orig_iata = ?, datetime_takeoff = ?,
                                        runway_takeoff = ?, dest_icao = ?, dest_iata = ?, datetime_landed = ?,
                                        runway_landed = ?, flight_time = ?, actual_distance = ?
                                    WHERE fr24_id = ?
                                """
                                update_values.append(flight.fr24_id)

                            cursor.execute(update_sql, update_values)

                            # Only count as updated if we filled missing data
                            if cursor.rowcount > 0 and (
                                provides_takeoff or provides_landing
                            ):
                                updated_count += 1

                    conn.commit()

        # Count flights not found in API response across all windows
        missing_ids = all_incomplete_flight_ids - all_found_flight_ids
        not_found_count = len(missing_ids)

        print(
            f"Found {len(all_incomplete_flight_ids)} total incomplete flights to update"
        )

        # Print summary using refactored utility
        summary_data: dict[str, int | str] = {
            "flights_fetched_from_api": total_fetched,
            "flights_updated": updated_count,
            "flights_not_found": not_found_count,
        }
        if missing_ids:
            summary_data["not_found_flight_ids"] = ", ".join(list(missing_ids))

        print_summary("UPDATE FLIGHTS SUMMARY", **summary_data)
        return updated_count, not_found_count
