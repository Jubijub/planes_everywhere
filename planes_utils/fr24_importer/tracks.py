"""Flight tracks import module for FlightRadar24 API integration."""

from dataclasses import dataclass
from datetime import datetime
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


@dataclass
class BoundingBox:
    """Represents a geographic bounding box."""

    latitude_min: float
    latitude_max: float
    longitude_min: float
    longitude_max: float

    def contains(self, lat: float, lon: float) -> bool:
        """Check if a point is within the bounding box."""
        return (
            self.latitude_min <= lat <= self.latitude_max
            and self.longitude_min <= lon <= self.longitude_max
        )


@dataclass
class Airport:
    """Represents an airport with IATA code, ICAO code, and runways."""

    iata: Optional[str]
    icao: Optional[str]
    runways: List[str]


def create_tracks_table(db_path: str) -> None:
    """Create the tracks table if it doesn't exist.

    Args:
        db_path: Path to the SQLite database file
    """
    with sqlite3.connect(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS tracks (
                fr24_id TEXT,
                timestamp TEXT,
                lat REAL,
                lon REAL,
                alt REAL,
                gspeed REAL,
                vspeed REAL,
                PRIMARY KEY (fr24_id, timestamp),
                FOREIGN KEY (fr24_id) REFERENCES flights (fr24_id)
            )
        """)
        conn.commit()


@handle_fr24_exceptions("tracks population")
def populate_tracks(
    db_path: str,
    bounding_box: BoundingBox,
    fr24_api_key: Optional[str] = None,
    plan: Optional[SubscriptionPlan] = None,
    origin_airport: Optional[Airport] = None,
    destination_airport: Optional[Airport] = None,
    start_datetime: Optional[datetime] = None,
    end_datetime: Optional[datetime] = None,
) -> Tuple[int, int, int, int]:
    """Populate tracks for complete flights within the specified bounding box.

    Args:
        db_path: Path to the SQLite database file
        bounding_box: Geographic bounding box to filter track points
        fr24_api_key: Optional FR24 API key. If None, uses FR24_API_TOKEN from environment.
        plan: Optional subscription plan for rate limiting. If None, no rate limiting is applied.
        origin_airport: Optional origin airport filter. If provided, only flights from this airport will be processed.
        destination_airport: Optional destination airport filter. If provided, only flights to this airport will be processed.
        start_datetime: Optional start datetime filter (must be timezone-naive UTC). If provided, only flights after this time will be processed.
        end_datetime: Optional end datetime filter (must be timezone-naive UTC). If provided, only flights before this time will be processed.

    Returns:
        Tuple of (flights_processed, track_points_fetched, track_points_inserted, flights_not_found)

    Raises:
        ValueError: If FR24_API_TOKEN not found in environment and fr24_api_key is None
        RateLimitError: If FR24 API rate limit is exceeded
        ApiError: If FR24 API returns an error
        Fr24SdkError: If FR24 SDK encounters an error
    """
    fr24_api_key = validate_api_key(fr24_api_key)

    # Create table if it doesn't exist
    create_tracks_table(db_path)

    # Get complete flights that don't have tracks yet
    complete_flight_ids = []

    with sqlite3.connect(db_path) as conn:
        cursor = conn.cursor()

        # Build the SQL query with optional filters
        query = """
            SELECT f.fr24_id
            FROM flights f
            WHERE f.requires_update = FALSE
              AND f.fr24_id NOT IN (SELECT DISTINCT fr24_id FROM tracks)
        """

        params = []

        # Add airport filters (OR between origin and destination)
        airport_conditions = []
        
        if origin_airport:
            runway_placeholders = ",".join(["?" for _ in origin_airport.runways])
            airport_conditions.append(f"((f.orig_icao = ? OR f.orig_iata = ?) AND f.runway_takeoff IN ({runway_placeholders}))")
            params.extend([origin_airport.icao, origin_airport.iata] + origin_airport.runways)
        
        if destination_airport:
            runway_placeholders = ",".join(["?" for _ in destination_airport.runways])
            airport_conditions.append(f"((f.dest_icao = ? OR f.dest_iata = ?) AND f.runway_landed IN ({runway_placeholders}))")
            params.extend([destination_airport.icao, destination_airport.iata] + destination_airport.runways)
        
        if airport_conditions:
            query += f" AND ({' OR '.join(airport_conditions)})"

        # Add datetime filters
        if start_datetime:
            query += " AND f.first_seen >= ?"
            params.append(start_datetime.isoformat() + "Z")

        if end_datetime:
            query += " AND f.first_seen <= ?"
            params.append(end_datetime.isoformat() + "Z")

        print(f"DEBUG: SQL Query: {query}")
        print(f"DEBUG: Parameters: {params}")
        
        cursor.execute(query, params)
        rows = cursor.fetchall()
        if not rows:
            print("No complete flights without tracks found")
            return 0, 0, 0, 0

        complete_flight_ids = [row[0] for row in rows]

    print(f"Found {len(complete_flight_ids)} complete flights to fetch tracks for")

    # Setup rate limiting
    sleep_time = setup_rate_limiting(plan)

    flights_processed = 0
    track_points_fetched = 0
    track_points_inserted = 0
    flights_not_found = 0

    with Client(api_token=fr24_api_key) as client:
        for i, fr24_id in enumerate(complete_flight_ids):
            print(f"Processing flight {i + 1}/{len(complete_flight_ids)}: {fr24_id}")

            # Apply rate limiting
            apply_rate_limit(sleep_time, is_first_request=(i == 0))

            try:
                tracks_response = client.flight_tracks.get(fr24_id)

                if not tracks_response.data:
                    print(f"  No track data found for flight {fr24_id}")
                    flights_not_found += 1
                    continue

                # API returns data=[FlightTracks(fr24_id='...', tracks=[FlightTrackPoint(...), ...])]
                # We need the tracks list from the first FlightTracks object
                flight_tracks = (
                    tracks_response.data[0] if tracks_response.data else None
                )
                if not flight_tracks or not flight_tracks.tracks:
                    print(f"  No track points found for flight {fr24_id}")
                    flights_not_found += 1
                    continue

                # Count all fetched points
                total_points = len(flight_tracks.tracks)
                track_points_fetched += total_points

                # Filter points within bounding box and exclude taxiing (alt=0 with low speed)
                track_points_to_insert = []
                for point in flight_tracks.tracks:
                    if bounding_box.contains(point.lat, point.lon):
                        # Skip taxiing points (altitude 0 with ground speed <= 20)
                        if point.alt == 0 and point.gspeed <= 20:
                            continue

                        track_points_to_insert.append(
                            (
                                fr24_id,
                                point.timestamp,
                                point.lat,
                                point.lon,
                                point.alt,
                                point.gspeed,
                                point.vspeed,
                            )
                        )

                if track_points_to_insert:
                    with sqlite3.connect(db_path) as conn:
                        cursor = conn.cursor()
                        cursor.executemany(
                            """
                            INSERT OR IGNORE INTO tracks 
                            (fr24_id, timestamp, lat, lon, alt, gspeed, vspeed)
                            VALUES (?, ?, ?, ?, ?, ?, ?)
                        """,
                            track_points_to_insert,
                        )
                        inserted_count = cursor.rowcount
                        track_points_inserted += inserted_count
                        conn.commit()

                    print(
                        f"  Fetched {total_points} points, inserted {len(track_points_to_insert)} (within bounding box)"
                    )
                else:
                    print(f"  Fetched {total_points} points, 0 within bounding box")

                flights_processed += 1

            except Exception as e:
                if "not found" in str(e).lower():
                    print(f"  Flight {fr24_id} not found in API")
                    flights_not_found += 1
                else:
                    print(f"  Error processing flight {fr24_id}: {e}")
                    continue

        # Print summary
        summary_data = {
            "flights_processed": flights_processed,
            "track_points_fetched": track_points_fetched,
            "track_points_inserted": track_points_inserted,
            "flights_not_found": flights_not_found,
        }
        print_summary("POPULATE TRACKS SUMMARY", **summary_data)

        return (
            flights_processed,
            track_points_fetched,
            track_points_inserted,
            flights_not_found,
        )
