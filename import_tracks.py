# Little utils to import tracks as a separate process from the colab, to allow analysis while tracks are importing.

import datetime
import os

from dotenv import load_dotenv

from planes_utils.fr24_importer import (
    SubscriptionPlan,
    UsagePeriod,
    getUsage,
    initialize_package,
)
from planes_utils.fr24_importer.tracks import Airport, BoundingBox, populate_tracks

# Parameters
start_datetime = datetime.datetime(2025, 8, 10, 0, 0)
end_datetime = datetime.datetime(2025, 8, 24, 23, 59)
bounding_box = BoundingBox(
    latitude_min=47.24, latitude_max=47.7, longitude_min=8.3, longitude_max=8.8
)
origin = Airport(icao=None, iata="ZRH", runways=["10", "14", "16", "28", "32", "34"])
destination = Airport(
    icao=None, iata="ZRH", runways=["10", "14", "16", "28", "32", "34"]
)


load_dotenv(override=True)
fr24_api_key = os.getenv("FR24_API_TOKEN")
plan = initialize_package(SubscriptionPlan.ESSENTIAL)

flights_processed, track_points_fetched, track_points_inserted, flights_not_found = (
    populate_tracks(
        "planes.sqlite3",
        bounding_box,
        fr24_api_key,
        plan,
        origin_airport=origin,
        destination_airport=destination,
        start_datetime=start_datetime,
        end_datetime=end_datetime,
    )
)
