"""Flask API for Air Quality Smart Dashboard."""
import os
from flask import Flask, jsonify, request, send_from_directory
from flask_cors import CORS
from data_loader import AirQualityDataLoader

app = Flask(__name__, static_folder='../frontend', static_url_path='')
CORS(app)

# Cache API responses for 5 minutes (data changes only on server restart)
@app.after_request
def add_cache_headers(response):
    if response.content_type == 'application/json':
        response.headers['Cache-Control'] = 'public, max-age=300'
    return response

# Load data once at startup
CSV_PATH = os.path.join(os.path.dirname(__file__), '..', 'all_cities_all_years.csv')
COORDS_PATH = os.path.join(os.path.dirname(__file__), 'city_coords.json')
print(f"[App] CSV path: {CSV_PATH}")
print(f"[App] Coords path: {COORDS_PATH}")

loader = AirQualityDataLoader(CSV_PATH, COORDS_PATH)


@app.route('/')
def index():
    """Serve the frontend dashboard."""
    response = send_from_directory(app.static_folder, 'air_quality_dashboard.html')
    response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
    response.headers['Pragma'] = 'no-cache'
    response.headers['Expires'] = '0'
    return response


@app.route('/api/overview')
def api_overview():
    """KPI overview: annual avg AQI, best/worst city, quality distribution, seasonal summary."""
    year = request.args.get('year', default=loader.years[-1], type=int)
    data = loader.get_overview(year)
    return jsonify(data)


@app.route('/api/temporal')
def api_temporal():
    """Temporal analysis: monthly trends, seasonal, YoY, moving averages, best/worst months."""
    year = request.args.get('year', default=loader.years[-1], type=int)
    city = request.args.get('city', default='all', type=str) or 'all'
    data = loader.get_temporal(year, city)
    return jsonify(data)


@app.route('/api/spatial')
def api_spatial():
    """Spatial analysis: city ranking, regional distribution, clusters, hotspots."""
    year = request.args.get('year', default=loader.years[-1], type=int)
    data = loader.get_spatial(year)
    return jsonify(data)


@app.route('/api/pollutants')
def api_pollutants():
    """Pollutant analysis: trends, correlation matrix, primary pollutant, PM ratio, composition."""
    year = request.args.get('year', default=loader.years[-1], type=int)
    city = request.args.get('city', default='all', type=str) or 'all'
    data = loader.get_pollutants(year, city)
    return jsonify(data)


@app.route('/api/quality')
def api_quality():
    """Quality level analysis: distribution, good ratio, heavy pollution frequency, transitions."""
    year = request.args.get('year', default=loader.years[-1], type=int)
    city = request.args.get('city', default='all', type=str) or 'all'
    data = loader.get_quality(year, city)
    return jsonify(data)


@app.route('/api/advanced')
def api_advanced():
    """Advanced analysis: seasonal decomposition, heatmap, pollution episodes, city similarity."""
    year = request.args.get('year', default=loader.years[-1], type=int)
    data = loader.get_advanced(year)
    return jsonify(data)


@app.route('/api/city/<city_name>')
def api_city_detail(city_name):
    """Complete per-city data for a given year."""
    year = request.args.get('year', default=loader.years[-1], type=int)
    data = loader.get_city_detail(city_name, year)
    return jsonify(data)


@app.route('/api/cities')
def api_cities():
    """List of all cities with coordinates."""
    data = loader.get_cities()
    return jsonify(data)


@app.route('/api/years')
def api_years():
    """List of available years."""
    data = loader.get_years()
    return jsonify(data)


if __name__ == '__main__':
    print("\n[App] Starting Flask server on http://localhost:5000")
    print("[App] Open your browser to view the dashboard.\n")
    app.run(host='0.0.0.0', port=5000, debug=True, use_reloader=False)
