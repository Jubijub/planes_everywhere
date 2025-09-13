# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Development Environment

This project uses Python 3.12+ with `uv` for dependency management. Key dependencies:
- `folium` - Interactive maps for flight visualization
- `fr24sdk` - FlightRadar24 API client
- `pandas` - Data analysis
- `jupyterlab` - Notebook environment
- `python-dotenv` - Environment variable management
- `requests` - HTTP client for OpenSky API

Development dependencies include `ruff` for linting.

## Development Commands

- **Install dependencies**: `uv sync`
- **Start JupyterLab**: `uv run jupyter lab`
- **Lint code**: `uv run ruff check`
- **Format code**: `uv run ruff format`

## Project Architecture

This is a flight data analysis project that integrates with multiple aviation APIs:

### Core Components

1. **Flight Data Sources**:
   - OpenSky Network API (primary) - Real-time flight state data
   - FlightRadar24 API - Historical flight tracking and detailed flight information
   
2. **Data Storage**:
   - SQLite database (`planes.sqlite3`) stores ICAO 8643 aircraft type designators
   - ICAO data is loaded from JSON files in `data/icao_8643_files/` directory

3. **Analysis Environment**:
   - Primary analysis in `Planes.ipynb` Jupyter notebook
   - Flight visualization using Folium maps
   - Flight track analysis and visualization

### Key Workflow

1. **Authentication**: Both APIs require credentials
   - OpenSky: OAuth2 client credentials flow using `credentials.json`
   - FlightRadar24: API token via `.env` file (`FR24_API_TOKEN`)

2. **Data Processing**:
   - ICAO aircraft database initialization from manufacturer JSON files
   - Flight data retrieval with bounding box filtering (focused on Zurich area)
   - Flight track visualization with altitude-based color coding

3. **Visualization**:
   - Interactive maps using Folium
   - Flight paths as polylines and circles
   - Altitude visualization with color gradients

### API Integration Notes

- OpenSky API endpoints: `/states/all`, `/flights/departure`, `/flights/arrival`, `/flights/all`, `/tracks/all`
- FlightRadar24 has rate limits (10-90 requests/minute) and response limits
- Flight data is time-windowed due to API response size constraints
- Both APIs support bounding box queries for geographic filtering

### Database Schema

The `icao_8643` table stores aircraft type information:
- Manufacturer, model details, engine specifications
- Aircraft descriptions and weight categories
- Uses `tdesig` field as unique identifier (matches flight API responses)