# Handling of ICAO8643 JSON files.

import glob
import json
from pathlib import Path
from typing import Any, Dict, List


def load_json_file(file_path: Path) -> List[Dict[str, Any]]:
    """Load and parse a JSON file."""
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)
            print(f"Loaded {len(data)} records from {file_path}")
            return data
    except (json.JSONDecodeError, FileNotFoundError) as e:
        print(f"Error loading {file_path}: {e}")
        return []


def prepare_record(record: Dict[str, Any]) -> Dict[str, Any]:
    """Clean and prepare a record for database insertion."""

    cleaned = {}

    # Convert engine_count to integer
    try:
        cleaned["engine_count"] = int(record.get("engine_count", 0))
    except (ValueError, TypeError):
        cleaned["engine_count"] = 0

    # Handle text fields with fallback logic for model_no and model_name
    text_fields = [
        "manufacturer_code",
        "model_no",
        "model_name",
        "model_version",
        "engine_type",
        "aircraft_desc",
        "description",
        "wtc",
        "tdesig",
        "wtg",
    ]

    # Apply fallback logic for model fields
    model_no = record.get("model_no")
    model_name = record.get("model_name")

    for field in text_fields:
        if field == "model_no":
            value = model_no or model_name
        elif field == "model_name":
            value = model_name or model_no
        else:
            value = record.get(field)

        if value is None or value == "":
            cleaned[field] = (
                None if field in ["model_name", "model_version", "wtg"] else ""
            )
        else:
            cleaned[field] = str(value)

    return cleaned
