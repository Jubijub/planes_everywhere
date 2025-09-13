# Planes Everywhere

Flight data analysis project that integrates with FlightRadar24 API to track and visualize aircraft movements around airports, with a focus on noise analysis and flight pattern visualization.

## Setup Instructions

### Prerequisites

- Python 3.12 or higher
- [uv](https://docs.astral.sh/uv/) - Fast Python package installer and resolver

### Installation

1. **Clone the repository**
   ```bash
   git clone <repository-url>
   cd planes_everywhere
   ```

2. **Install dependencies using uv**
   ```bash
   uv sync
   ```
   This will create a virtual environment and install all required dependencies automatically. On a new machine, `uv sync` will restore the virtual environment based on the `uv.lock` file.

3. **Set up API credentials**

   #### FlightRadar24 API
   - Create a `.env` file in the project root:
     ```bash
     FR24_API_TOKEN=your-fr24-api-token
     ```
   - Get your API token from [FlightRadar24 API Key Management](https://fr24api.flightradar24.com/key-management)
   - For testing, you can use `.env.test` for sandbox mode (doesn't cost credits)

4. **Initialize the aircraft database**
   - Download ICAO 8643 aircraft type data:
     - Visit [ICAO Data Services](https://applications.icao.int/dataservices/default.aspx)
     - Fill the form to obtain a trial key by email
     - Enter the trial key in the "Start using the API" box
     - Search for `DOC8643` and click on this line
     - Download JSON files for each manufacturer (see list below)
     - Save the JSON files in `data/icao_8643_files/` directory

   **Manufacturer names for ICAO data:**
   - AEROSPATIALE, AGUSTA, AGUSTAWESTLAND, AIRBUS, AIRBUS HELICOPTERS
   - AIRBUS HELICOPTERS-HARBIN, ANTONOV, ATR, BEECHCRAFT, BELL
   - BOEING, BOMBARDIER, CESSNA, CIRRUS, DASSAULT, DIAMOND
   - EMBRAER, GULFSTREAM AEROSPACE, ILYUSHIN, LEARJET, LEONARDO
   - MOONEY, PILATUS, PIPER, ROBINSON, SAAB, SIKORSKY, TUPOLEV

### Running the Project

1. **Start JupyterLab**
   ```bash
   uv run jupyter lab
   ```

2. **If you just want to check the results**

   - Navigate to `Planes_light.ipynb` in Jupyterlab
   - It's the same as `Planes.ipynb` but without the map, to make it lighter   

3. **Open the main analysis notebook**
   - Navigate to `Planes.ipynb` in JupyterLab
   - Follow the notebook cells to:
     - Set up API authentication
     - Import ICAO aircraft data
     - Configure analysis parameters (airport, date range, bounding box)
     - Retrieve flight information
     - Populate flight tracks
     - Analyze and visualize flight patterns

### Development Commands

- **Lint code**: `uv run ruff check`
- **Format code**: `uv run ruff format`
- **Install new dependencies**: `uv add package-name`
- **Update dependencies**: `uv sync`
- **Import tracks (separate process)**: `uv run import_tracks.py`

### Project Structure

planes_everywhere/
|-- Planes.ipynb              # Main analysis notebook
|-- planes_utils/             # Python utility modules
|   |-- fr24_importer/        # FlightRadar24 API integration
|   |-- icao8643.py           # ICAO aircraft data processing
|   `-- noise/                # Noise analysis utilities
|-- data/
|   `-- icao_8643_files/      # ICAO aircraft type JSON files
|-- planes.sqlite3            # SQLite database (created automatically)
|-- .env                      # FlightRadar24 API token (you create)
`-- region-of-interest-DEM.tif # Digital Elevation Model (auto-downloaded)
```

### Key Features

- **FlightRadar24 Integration**: Flight tracking using FlightRadar24 API
- **Interactive Visualization**: Flight path visualization with Folium maps, altitude-based color coding
- **Noise Analysis**: Aircraft noise calculations based on distance, altitude, and aircraft type
- **Flight Pattern Analysis**: Analysis by runway usage, time of day, weekday/weekend patterns
- **Geographic Filtering**: Bounding box queries for specific geographic areas (focused on Zurich)
- **Aircraft Database**: SQLite storage of ICAO 8643 aircraft specifications

### API Integration Details

#### FlightRadar24 Features:
- Flight Summary Full API for detailed flight information
- Rate limits: 10-90 requests/minute depending on subscription
- Response limits: 20-300 items per response
- Track data costs 40 credits per call

### Database Schema

The `icao_8643` table stores aircraft type information:
- Manufacturer, model details, engine specifications
- Aircraft descriptions and weight categories
- Uses `tdesig` field as unique identifier (matches flight API responses)
- ~2/3 of manufacturer records are deduplicated by `tdesig`

### Troubleshooting

- **API Authentication**: Ensure FR24_API_TOKEN is correctly set in `.env` file
- **ICAO Data**: Check that `data/icao_8643_files/` contains the required JSON files
- **Python Version**: Verify Python 3.12+ is installed and accessible to uv
- **Virtual Environment**: If issues occur, try `uv sync --reinstall` to recreate the environment
- **Rate Limits**: Monitor API usage - FlightRadar24 has strict limits and costs
- **Large Data Sets**: Flight track import is expensive - use time windows and geographic filtering

### Performance Notes

- Flight data is time-windowed due to API response size constraints
- Track data retrieval is rate-limited and expensive - use the separate `import_tracks.py` script for bulk processing
- Database operations are optimized for the Zurich airport area (LSZH) but can be adapted for other locations