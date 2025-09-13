# Logic to calculate the distance between a POI and a plane (from its track).

from dataclasses import dataclass
from enum import Enum
import math
import sqlite3
from typing import List, Optional, Tuple


class DistanceType(Enum):
    """Enum to specify 2D or 3D distance calculation."""
    TWO_D = "2d"
    THREE_D = "3d"


@dataclass
class POI:
    """Point of Interest with 3D coordinates."""

    latitude: float
    longitude: float
    altitude: float  # in meters


@dataclass
class TrackPoint:
    """Track point with 3D coordinates and timestamp."""

    latitude: float
    longitude: float
    altitude: float  # in feet (from FlightRadar24 API)
    timestamp: str


def haversine_distance(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Calculate the great circle distance between two points on Earth in meters.

    Args:
        lat1, lon1: Coordinates of first point
        lat2, lon2: Coordinates of second point

    Returns:
        Distance in meters
    """
    # Convert latitude and longitude from degrees to radians
    lat1, lon1, lat2, lon2 = map(math.radians, [lat1, lon1, lat2, lon2])

    # Haversine formula
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    a = (
        math.sin(dlat / 2) ** 2
        + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    )
    c = 2 * math.asin(math.sqrt(a))

    # Radius of earth in meters
    r = 6371000

    return c * r


def distance_3d(poi: POI, lat: float, lon: float, alt: float) -> float:
    """Calculate 3D distance between POI and a point.

    Args:
        poi: Point of interest
        lat, lon, alt: Coordinates of the point (altitude in feet)

    Returns:
        3D distance in meters
    """
    # Horizontal distance using haversine formula
    horizontal_distance = haversine_distance(poi.latitude, poi.longitude, lat, lon)

    # Convert altitude from feet to meters (1 foot = 0.3048 meters)
    alt_meters = alt * 0.3048

    # Vertical distance
    vertical_distance = abs(poi.altitude - alt_meters)

    # 3D distance using Pythagorean theorem
    return math.sqrt(horizontal_distance**2 + vertical_distance**2)


def interpolate_track_segment(
    point1: TrackPoint,
    point2: TrackPoint,
    poi: POI,
    distance_type: DistanceType,
    num_interpolation_points: int = 100,
) -> Tuple[float, float, float, float]:
    """Find the closest point on a track segment to the POI using interpolation.

    Args:
        point1: First track point
        point2: Second track point
        poi: Point of interest
        distance_type: Whether to calculate 2D or 3D distance
        num_interpolation_points: Number of points to interpolate between track points

    Returns:
        Tuple of (min_distance, closest_lat, closest_lon, closest_alt)
        For 2D calculations, closest_alt will be interpolated but not used in distance calculation
    """
    min_distance = float("inf")
    closest_lat = closest_lon = closest_alt = 0.0

    # Linear interpolation between the two points
    for i in range(num_interpolation_points + 1):
        t = i / num_interpolation_points  # Parameter from 0 to 1

        # Linear interpolation
        interp_lat = point1.latitude + t * (point2.latitude - point1.latitude)
        interp_lon = point1.longitude + t * (point2.longitude - point1.longitude)
        interp_alt = point1.altitude + t * (point2.altitude - point1.altitude)

        # Calculate distance to POI based on type
        if distance_type == DistanceType.TWO_D:
            distance = haversine_distance(poi.latitude, poi.longitude, interp_lat, interp_lon)
        else:  # THREE_D
            distance = distance_3d(poi, interp_lat, interp_lon, interp_alt)

        if distance < min_distance:
            min_distance = distance
            closest_lat = interp_lat
            closest_lon = interp_lon
            closest_alt = interp_alt

    return min_distance, closest_lat, closest_lon, closest_alt


def get_flight_tracks(
    fr24_id: str, db_path: str = "planes.sqlite3"
) -> List[TrackPoint]:
    """Get track points for a flight from the database.

    Args:
        fr24_id: Flight ID
        db_path: Path to SQLite database

    Returns:
        List of track points ordered by timestamp
    """
    tracks = []

    try:
        with sqlite3.connect(db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT lat, lon, alt, timestamp
                FROM tracks
                WHERE fr24_id = ?
                ORDER BY timestamp
                """,
                (fr24_id,),
            )

            for row in cursor.fetchall():
                lat, lon, alt, timestamp = row
                tracks.append(
                    TrackPoint(
                        latitude=lat, longitude=lon, altitude=alt, timestamp=timestamp
                    )
                )

    except Exception as e:
        print(f"Error fetching tracks for flight {fr24_id}: {e}")

    return tracks


def get_min_distance_with_details(
    fr24_id: str, poi: POI, distance_type: DistanceType, db_path: str = "planes.sqlite3"
) -> Optional[Tuple[float, float, float, float]]:
    """Calculate minimum distance with details of the closest point.

    Args:
        fr24_id: Flight ID
        poi: Point of interest with 3D coordinates
        distance_type: Whether to calculate 2D or 3D distance
        db_path: Path to SQLite database

    Returns:
        Tuple of (min_distance, closest_lat, closest_lon, closest_alt) or None
        For 2D calculations, closest_alt is still returned but distance ignores altitude
    """
    # Get flight tracks
    tracks = get_flight_tracks(fr24_id, db_path)

    if len(tracks) < 2:
        return None  # Need at least 2 points to interpolate

    min_distance = float("inf")
    best_lat = best_lon = best_alt = 0.0

    # Check each track segment
    for i in range(len(tracks) - 1):
        point1 = tracks[i]
        point2 = tracks[i + 1]

        # Find closest point on this segment
        segment_min_distance, closest_lat, closest_lon, closest_alt = (
            interpolate_track_segment(point1, point2, poi, distance_type)
        )

        if segment_min_distance < min_distance:
            min_distance = segment_min_distance
            best_lat = closest_lat
            best_lon = closest_lon
            best_alt = closest_alt

    if min_distance == float("inf"):
        return None

    return min_distance, best_lat, best_lon, best_alt


def get_min_distance(
    fr24_id: str, poi: POI, distance_type: DistanceType, db_path: str = "planes.sqlite3"
) -> Optional[float]:
    """Calculate the minimum distance from a flight to a point of interest.

    This is a convenience function that returns only the distance.

    Args:
        fr24_id: Flight ID
        poi: Point of interest with 3D coordinates
        distance_type: Whether to calculate 2D or 3D distance
        db_path: Path to SQLite database

    Returns:
        Minimum distance in meters, or None if no tracks found
    """
    result = get_min_distance_with_details(fr24_id, poi, distance_type, db_path)
    return result[0] if result else None

