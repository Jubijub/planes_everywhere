# Logic to calculate the altitude of a point of interest given its latitude / longitude.

import os
from pathlib import Path
import subprocess
from typing import Optional

import rasterio

from ..fr24_importer.tracks import BoundingBox


def download_elevation_data(
    bounding_box: BoundingBox,
    output_file: str = "region-of-interest-DEM.tif",
    product: str = "SRTM1",
    clean_cache: bool = True,
) -> bool:
    """Download elevation data for a given bounding box using the elevation package.

    Args:
        bounding_box: BoundingBox object defining the area of interest
        output_file: Output filename for the DEM file (default: "region-of-interest-DEM.tif")
        product: SRTM product to use - "SRTM1" (30m) or "SRTM3" (90m) (default: "SRTM1")
        clean_cache: Whether to clean the cache before downloading (default: True)

    Returns:
        bool: True if download was successful, False otherwise
    """
    # Remove existing file if it exists
    if os.path.exists(output_file):
        print(f"🗑️ Removing existing file: {output_file}")
        os.remove(output_file)

    # Prepare the eio command with specified product and bounding box coordinates
    eio_command = [
        "eio",
        "--product",
        product,
        "clip",
        "-o",
        output_file,
        "--bounds",
        str(bounding_box.longitude_min),
        str(bounding_box.latitude_min),
        str(bounding_box.longitude_max),
        str(bounding_box.latitude_max),
    ]

    print(f"Running command: {' '.join(eio_command)}")

    # Clean cache first as preventive measure
    if clean_cache:
        print(f"🧹 Cleaning {product} cache first...")
        try:
            subprocess.run(
                ["eio", "--product", product, "clean"], capture_output=True, text=True
            )
            print("Cache cleaned successfully")
        except:
            print("Cache clean failed, but continuing...")

    try:
        # Run the eio command
        result = subprocess.run(eio_command, capture_output=True, text=True, check=True)
        print("✅ DEM download completed successfully!")
        print(f"Output: {result.stdout}")
        if result.stderr:
            print(f"Warnings: {result.stderr}")

        # Verify file was created
        if os.path.exists(output_file):
            print(f"🎉 DEM file created successfully: {output_file}")
            return True
        else:
            print("⚠️ DEM file was not created")
            return False

    except subprocess.CalledProcessError as e:
        print(f"❌ Error running eio command: {e}")
        print(f"Return code: {e.returncode}")
        print(f"stdout: {e.stdout}")
        print(f"stderr: {e.stderr}")

        # If it still fails, suggest fallback
        if product == "SRTM1":
            print("\n⚠️ SRTM1 download failed. Consider trying SRTM3 as fallback:")
            print("Call the function with product='SRTM3' for 30m resolution data")

        return False

    except FileNotFoundError:
        print(
            "❌ Error: 'eio' command not found. Please install elevation package with: pip install elevation"
        )
        return False


def get_altitude(
    latitude: float, longitude: float, dem_file: str = "region-of-interest-DEM.tif"
) -> Optional[float]:
    """Get altitude at specific coordinates from a DEM file.

    Args:
        latitude: Latitude coordinate
        longitude: Longitude coordinate
        dem_file: Path to the DEM raster file (default: "region-of-interest-DEM.tif")

    Returns:
        float: Elevation in meters, or None if unable to determine
    """
    if not os.path.exists(dem_file):
        return None

    try:
        with rasterio.open(dem_file) as src:
            # Sample the elevation at the coordinates
            # rasterio.sample returns an iterator of arrays, one per coordinate pair
            coords = [
                (longitude, latitude)
            ]  # Note: rasterio expects (x, y) = (longitude, latitude)
            elevation_values = list(src.sample(coords))

            if elevation_values and len(elevation_values[0]) > 0:
                elevation = elevation_values[0][0]  # First band, first coordinate

                # Handle NoData values
                if elevation == src.nodata or elevation < -1000 or elevation > 10000:
                    return None
                else:
                    return float(elevation)
            else:
                return None

    except Exception:
        return None
