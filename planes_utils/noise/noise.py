import math
import sqlite3
from typing import Dict, Optional, Tuple

from .distance import POI


def get_aircraft_noise_data(aircraft_type: str, db_path: str = "planes.sqlite3") -> Optional[Dict]:
    """Get aircraft noise and specification data from the database.
    
    Args:
        aircraft_type: ICAO aircraft type designator (e.g., 'B738', 'A320')
        db_path: Path to SQLite database
        
    Returns:
        Dictionary with aircraft data including wtc (wake turbulence category) and other specs,
        or None if not found
    """
    try:
        with sqlite3.connect(db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT tdesig, manufacturer_code, model_no, model_name, wtc, engine_count, engine_type, aircraft_desc
                FROM icao_8643 
                WHERE tdesig = ?
                """,
                (aircraft_type,)
            )
            row = cursor.fetchone()
            if row:
                return {
                    'type_designator': row[0],
                    'manufacturer': row[1],
                    'model': row[2],
                    'type_name': row[3],
                    'wake_category': row[4],  # L=Light, M=Medium, H=Heavy, J=Super
                    'engines': row[5],
                    'engine_type': row[6],    # P=Piston, T=Turboprop, J=Jet
                    'aircraft_category': row[7]
                }
    except Exception as e:
        print(f"Error fetching aircraft data for {aircraft_type}: {e}")
    
    return None


def get_baseline_noise_by_category(wake_category: str, engine_type: str) -> float:
    """Get baseline noise level in EPNdB based on aircraft category.
    
    This provides approximate baseline noise levels based on ICAO categories.
    In a production system, these would be sourced from the French noise database
    or similar certified noise databases.
    
    Args:
        wake_category: Wake turbulence category (L, M, H, J)
        engine_type: Engine type (P, T, J)
        
    Returns:
        Baseline noise level in EPNdB at reference conditions
    """
    # Baseline noise levels (EPNdB) at reference distance (typically flyover)
    # These are approximations - real implementation should use certified data
    baseline_noise = {
        # Jet aircraft
        ('L', 'J'): 85,   # Light jets (regional jets, business jets)
        ('M', 'J'): 95,   # Medium jets (A320, B737 family)
        ('H', 'J'): 105,  # Heavy jets (A330, B777, etc.)
        ('J', 'J'): 110,  # Super heavy (A380, B747-8)
        
        # Turboprop aircraft
        ('L', 'T'): 80,   # Light turboprops
        ('M', 'T'): 88,   # Medium turboprops
        ('H', 'T'): 92,   # Heavy turboprops (rare)
        
        # Piston aircraft
        ('L', 'P'): 75,   # Light piston aircraft
        ('M', 'P'): 78,   # Medium piston aircraft
    }
    
    return baseline_noise.get((wake_category, engine_type), 90)  # Default fallback


def calculate_distance_attenuation(distance_meters: float) -> float:
    """Calculate noise attenuation due to distance using ICAO principles.
    
    Based on spherical spreading and atmospheric absorption.
    Reference distance is typically 1000m for flyover measurements.
    
    Args:
        distance_meters: Distance from aircraft to POI in meters
        
    Returns:
        Attenuation in dB (positive value indicates noise reduction)
    """
    if distance_meters <= 0:
        return 0.0
    
    reference_distance = 1000.0  # meters (typical ICAO reference)
    
    # Spherical spreading: 20*log10(d2/d1)
    spreading_loss = 20 * math.log10(distance_meters / reference_distance)
    
    # Atmospheric absorption (simplified model)
    # Real implementation would consider frequency, temperature, humidity
    # This is a simplified approximation for mid-frequency noise
    atmospheric_absorption = 0.005 * (distance_meters - reference_distance) / 100
    
    return spreading_loss + atmospheric_absorption


def calculate_altitude_correction(aircraft_altitude: float, poi_altitude: float) -> float:
    """Calculate noise correction based on altitude difference.
    
    Aircraft at higher altitudes relative to POI will have additional attenuation.
    
    Args:
        aircraft_altitude: Aircraft altitude in feet (from FlightRadar24 API)
        poi_altitude: POI altitude in meters
        
    Returns:
        Additional attenuation in dB
    """
    # Convert aircraft altitude from feet to meters
    aircraft_altitude_meters = aircraft_altitude * 0.3048
    
    altitude_diff = abs(aircraft_altitude_meters - poi_altitude)
    
    # Additional attenuation for altitude (simplified model)
    # Every 1000m of altitude difference adds ~2dB attenuation
    altitude_attenuation = (altitude_diff / 1000.0) * 2.0
    
    return altitude_attenuation


def calculate_aircraft_noise(
    fr24_id: str, 
    poi: POI, 
    db_path: str = "planes.sqlite3"
) -> Optional[Tuple[float, Dict]]:
    """Calculate the noise level of an aircraft as perceived at a POI.
    
    This function integrates aircraft specifications, distance calculations,
    and ICAO-based noise modeling to estimate perceived noise levels.
    
    Args:
        fr24_id: Flight ID to analyze
        poi: Point of Interest with 3D coordinates
        db_path: Path to SQLite database
        
    Returns:
        Tuple of (noise_level_epndb, details_dict) or None if calculation fails
        
    Details dict contains:
        - aircraft_type: ICAO type designator
        - manufacturer: Aircraft manufacturer  
        - model: Aircraft model
        - wake_category: Wake turbulence category
        - min_distance: Minimum distance to POI in meters
        - baseline_noise: Baseline noise in EPNdB
        - distance_attenuation: Attenuation due to distance
        - altitude_correction: Additional altitude correction
        - final_noise: Final calculated noise level
    """
    # Get flight details to determine aircraft type
    try:
        with sqlite3.connect(db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT type, runway_takeoff, runway_landed
                FROM flights 
                WHERE fr24_id = ?
                """,
                (fr24_id,)
            )
            flight_row = cursor.fetchone()
            if not flight_row:
                return None
            
            aircraft_type = flight_row[0]
    except Exception as e:
        print(f"Error fetching flight data for {fr24_id}: {e}")
        return None
    
    # Get aircraft specifications
    aircraft_data = get_aircraft_noise_data(aircraft_type, db_path)
    if not aircraft_data:
        return None
    
    # Get minimum distance and closest point details
    from .distance import DistanceType, get_min_distance_with_details
    distance_result = get_min_distance_with_details(fr24_id, poi, DistanceType.THREE_D, db_path)
    if not distance_result:
        return None
    
    min_distance, _, _, closest_alt = distance_result
    
    # Calculate baseline noise for this aircraft category
    baseline_noise = get_baseline_noise_by_category(
        aircraft_data['wake_category'], 
        aircraft_data['engine_type']
    )
    
    # Calculate distance attenuation
    distance_attenuation = calculate_distance_attenuation(min_distance)
    
    # Calculate altitude correction
    altitude_correction = calculate_altitude_correction(closest_alt, poi.altitude)
    
    # Final noise calculation
    final_noise = baseline_noise - distance_attenuation - altitude_correction
    
    # Ensure noise doesn't go below background level
    final_noise = max(final_noise, 30.0)  # Minimum background noise level
    
    details = {
        'aircraft_type': aircraft_data['type_designator'],
        'manufacturer': aircraft_data['manufacturer'],
        'model': aircraft_data['model'],
        'wake_category': aircraft_data['wake_category'],
        'engine_type': aircraft_data['engine_type'],
        'min_distance': min_distance,
        'closest_altitude': closest_alt,
        'baseline_noise': baseline_noise,
        'distance_attenuation': distance_attenuation,
        'altitude_correction': altitude_correction,
        'final_noise': final_noise
    }
    
    return final_noise, details


def calculate_multiple_flights_noise(
    flight_ids: list, 
    poi: POI, 
    db_path: str = "planes.sqlite3"
) -> Dict[str, Tuple[float, Dict]]:
    """Calculate noise levels for multiple flights at a POI.
    
    Args:
        flight_ids: List of flight IDs to analyze
        poi: Point of Interest with 3D coordinates
        db_path: Path to SQLite database
        
    Returns:
        Dictionary mapping flight_id to (noise_level, details) tuples
    """
    results = {}
    
    for flight_id in flight_ids:
        noise_result = calculate_aircraft_noise(flight_id, poi, db_path)
        if noise_result:
            results[flight_id] = noise_result
        else:
            print(f"Could not calculate noise for flight {flight_id}")
    
    return results