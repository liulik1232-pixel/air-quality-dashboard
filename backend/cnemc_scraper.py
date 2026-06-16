"""
CNEMC Air Quality Data Scraper
Fetches real-time air quality data from air.cnemc.cn:18007

Data flow:
  1. Get all provinces → cities via API
  2. For each city, fetch station-level data with actual concentrations
  3. Aggregate station data to city-level means
  4. Save to CSV (matching existing format) or MySQL records table

Usage:
  python cnemc_scraper.py                   # scrape once, save to CSV
  python cnemc_scraper.py --mode daily      # use daily data endpoint
  python cnemc_scraper.py --to-db           # save to MySQL records table
  python cnemc_scraper.py --interval 3600   # run every hour (daemon mode)
"""
import argparse
import json
import os
import re
import random
import sys
import time
import urllib.parse
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone, timedelta

import requests
import pandas as pd
import numpy as np

BASE_URL = "https://air.cnemc.cn:18007"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "application/json, text/javascript, */*; q=0.01",
    "Accept-Language": "zh-CN,zh;q=0.9",
    "X-Requested-With": "XMLHttpRequest",
    "Referer": f"{BASE_URL}/",
}
REQUEST_TIMEOUT = 15
MAX_WORKERS = 2
BATCH_DELAY = 0.3  # seconds between batches
MAX_RETRIES_PER_CITY = 2

QUALITY_LEVEL_MAP = {
    "优": 1, "良": 2, "轻度污染": 3, "中度污染": 4, "重度污染": 5, "严重污染": 6,
}

SEASON_MAP = {
    3: "春", 4: "春", 5: "春",
    6: "夏", 7: "夏", 8: "夏",
    9: "秋", 10: "秋", 11: "秋",
    12: "冬", 1: "冬", 2: "冬",
}

CSV_COLUMNS = [
    "地区", "日期", "质量等级", "AQI指数", "当天AQI排名",
    "PM2.5", "PM10", "So2", "No2", "Co", "O3",
    "年份", "月份", "季节", "等级编码",
]

def _get_json(url, method="GET", **kwargs):
    """Fetch JSON from CNEMC API with retry and exponential backoff."""
    for attempt in range(4):
        try:
            if method == "POST":
                resp = requests.post(f"{BASE_URL}/{url}", headers=HEADERS,
                                     timeout=REQUEST_TIMEOUT,
                                     data=kwargs.pop("data", {}), **kwargs)
            else:
                resp = requests.get(f"{BASE_URL}/{url}", headers=HEADERS,
                                    timeout=REQUEST_TIMEOUT, **kwargs)
            resp.raise_for_status()
            return resp.json()
        except requests.exceptions.Timeout:
            if attempt < 3:
                time.sleep(2 ** attempt)
        except Exception:
            if attempt < 3:
                time.sleep(1 + attempt * 2)
            else:
                return None
    return None


def get_provinces():
    """Fetch all provinces."""
    data = _get_json("CityData/GetProvince")
    if not data:
        return []
    return [(p["Id"], p["ProvinceName"]) for p in data
            if p["ProvinceName"] not in ("台湾", "香港", "澳门")]


def get_cities(province_id):
    """Fetch cities for a province."""
    data = _get_json(f"CityData/GetCitiesByPid?pid={province_id}")
    if not data:
        return []
    return [(c["CityCode"], c["CityName"]) for c in data]


def get_all_cities():
    """Get all cities across all provinces."""
    provinces = get_provinces()
    print(f"[*] Found {len(provinces)} provinces")

    all_cities = []
    for pid, pname in provinces:
        cities = get_cities(pid)
        all_cities.extend(cities)
        print(f"  {pname}: {len(cities)} cities")

    print(f"[*] Total: {len(all_cities)} cities")
    return all_cities


def get_station_data(city_name):
    """Fetch station-level data for a city. Returns list of station records."""
    encoded = urllib.parse.quote(city_name)
    data = _get_json(f"CityData/GetAQIDataPublishLive?cityName={encoded}")
    if data is None:
        return None
    return data


def parse_ms_timestamp(ts_str):
    """Parse ASP.NET /Date(milliseconds)/ format."""
    m = re.search(r"Date\((\d+)\)", ts_str)
    if m:
        ms = int(m.group(1))
        # Beijing time = UTC+8
        return datetime.fromtimestamp(ms / 1000, tz=timezone(timedelta(hours=8)))
    return None


def _parse_num(val):
    """Parse numeric value from API response. Handles '<3', '3~5', 'NA', etc."""
    if val is None:
        return None
    if isinstance(val, (int, float)):
        return float(val)
    s = str(val).strip()
    if not s or s.upper() in ("NA", "—", "-", "N/A"):
        return None
    # Remove <, >, ≤, ≥ prefixes and ~ ranges (take the midpoint or second value)
    s = re.sub(r"^[<≤>≥]", "", s)
    if "~" in s:
        parts = [float(x) for x in s.split("~") if x.strip()]
        return sum(parts) / len(parts) if parts else None
    try:
        return float(s)
    except ValueError:
        return None


def aggregate_stations(stations, city_name, city_code):
    """
    Aggregate station-level data to city-level.
    Returns a dict matching the CSV schema, or None if no valid data.
    """
    if not stations:
        return None

    values = {
        "AQI": [], "PM2_5": [], "PM10": [], "SO2": [], "NO2": [], "CO": [], "O3": [],
    }

    qualities = []
    primary_pollutants = []
    timepoints = set()

    for s in stations:
        try:
            aqi = _parse_num(s.get("AQI", 0))
            pm25 = _parse_num(s.get("PM2_5", 0))
            pm10 = _parse_num(s.get("PM10", 0))
            so2 = _parse_num(s.get("SO2", 0))
            no2 = _parse_num(s.get("NO2", 0))
            co = _parse_num(s.get("CO", 0))
            o3 = _parse_num(s.get("O3", 0))
        except (ValueError, TypeError):
            continue

        if all(v is None for v in [aqi, pm25, pm10, so2, no2, co, o3]):
            continue

        values["AQI"].append(aqi if aqi is not None else 0)
        values["PM2_5"].append(pm25 if pm25 is not None else 0)
        values["PM10"].append(pm10 if pm10 is not None else 0)
        values["SO2"].append(so2 if so2 is not None else 0)
        values["NO2"].append(no2 if no2 is not None else 0)
        values["CO"].append(co if co is not None else 0)
        values["O3"].append(o3 if o3 is not None else 0)

        if s.get("Quality"):
            qualities.append(s["Quality"])
        if s.get("PrimaryPollutant") and s["PrimaryPollutant"] != "—":
            primary_pollutants.append(s["PrimaryPollutant"])

        tp = s.get("TimePoint", "")
        if tp:
            ts = parse_ms_timestamp(tp) if "Date" in tp else None
            if ts is None:
                try:
                    ts = datetime.fromisoformat(tp)
                except (ValueError, TypeError):
                    pass
            if ts:
                timepoints.add(ts)

    if not values["AQI"]:
        return None

    def safe_mean(arr):
        return round(np.mean(arr), 3) if arr else 0

    avg_aqi = round(np.mean(values["AQI"]), 1)
    pm25_vals = [v for v in values["PM2_5"] if v > 0]
    pm10_vals = [v for v in values["PM10"] if v > 0]
    so2_vals = [v for v in values["SO2"] if v > 0]
    no2_vals = [v for v in values["NO2"] if v > 0]
    co_vals = [v for v in values["CO"] if v > 0]
    o3_vals = [v for v in values["O3"] if v > 0]
    avg_pm25 = round(float(np.mean(pm25_vals)), 1) if pm25_vals else 0.0
    avg_pm10 = round(float(np.mean(pm10_vals)), 1) if pm10_vals else 0.0
    avg_so2 = round(float(np.mean(so2_vals)), 1) if so2_vals else 0.0
    avg_no2 = round(float(np.mean(no2_vals)), 1) if no2_vals else 0.0
    avg_co = round(float(np.mean(co_vals)), 3) if co_vals else 0.0
    avg_o3 = round(float(np.mean(o3_vals)), 1) if o3_vals else 0.0

    # Determine quality level from average AQI
    if avg_aqi <= 50:
        quality = "优"
    elif avg_aqi <= 100:
        quality = "良"
    elif avg_aqi <= 150:
        quality = "轻度污染"
    elif avg_aqi <= 200:
        quality = "中度污染"
    elif avg_aqi <= 300:
        quality = "重度污染"
    else:
        quality = "严重污染"

    level_code = QUALITY_LEVEL_MAP.get(quality, 0)

    # Use most common timestamp
    ts = max(timepoints, key=lambda t: len([x for x in timepoints if x == t])) if timepoints else datetime.now()
    date_str = ts.strftime("%Y-%m-%d")

    return {
        "地区": city_name,
        "日期": date_str,
        "质量等级": quality,
        "AQI指数": avg_aqi,
        "当天AQI排名": None,
        "PM2.5": avg_pm25,
        "PM10": avg_pm10,
        "So2": avg_so2,
        "No2": avg_no2,
        "Co": avg_co,
        "O3": avg_o3,
        "年份": ts.year,
        "月份": ts.month,
        "季节": SEASON_MAP.get(ts.month, ""),
        "等级编码": level_code,
    }


def scrape_city(city_code, city_name):
    """Scrape a single city: fetch stations → aggregate → return row dict."""
    time.sleep(random.uniform(0.05, 0.2))  # jitter to avoid thundering herd
    stations = get_station_data(city_name)

    # Fallback: try without "市" suffix
    if not stations and city_name.endswith("市"):
        stations = get_station_data(city_name.rstrip("市"))

    if not stations:
        return None

    row = aggregate_stations(stations, city_name, city_code)
    if row:
        row["当天AQI排名"] = None  # will be filled later
    return row


def scrape_all_cities(cities, max_workers=MAX_WORKERS):
    """Scrape all cities concurrently with retry for failed ones."""
    results = {}
    pending = list(cities)

    for retry_round in range(MAX_RETRIES_PER_CITY + 1):
        if not pending:
            break

        if retry_round > 0:
            print(f"\n[*] Retry round {retry_round}: {len(pending)} cities ...")
            time.sleep(3)  # pause before retrying

        round_failed = []
        total = len(pending)

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_map = {
                executor.submit(scrape_city, code, name): (code, name)
                for code, name in pending
            }

            completed = 0
            for future in as_completed(future_map):
                code, name = future_map[future]
                completed += 1
                try:
                    row = future.result()
                    if row:
                        results[name] = row
                    else:
                        round_failed.append((code, name))
                except Exception as e:
                    print(f"  [!] {name} ({code}): {e}")
                    round_failed.append((code, name))

                if completed % 50 == 0:
                    print(f"  [{completed}/{total}] {len(results)} ok, "
                          f"{len(round_failed)} fail (round {retry_round})")
                time.sleep(0.1)

        pending = round_failed

    result_list = list(results.values())
    result_list.sort(key=lambda x: x["AQI指数"], reverse=True)
    for i, row in enumerate(result_list):
        row["当天AQI排名"] = i + 1

    truly_failed = [name for _, name in pending]
    print(f"\n[*] Done: {len(result_list)} cities scraped, {len(truly_failed)} failed")
    if truly_failed:
        print(f"  Failed: {truly_failed}")

    return result_list


def save_to_csv(rows, output_path, mode="a"):
    """Save rows to CSV. If mode='a' and file exists, append without header."""
    df = pd.DataFrame(rows, columns=CSV_COLUMNS)
    df = df.sort_values(["日期", "地区"])
    df = df.fillna(0)  # replace NaN with 0 for any edge cases

    file_exists = os.path.exists(output_path)
    if mode == "a" and file_exists:
        # Check for duplicates by (地区, 日期)
        existing = pd.read_csv(output_path, encoding="utf-8-sig", low_memory=False)
        existing["日期"] = existing["日期"].astype(str)
        df["日期"] = df["日期"].astype(str)
        merged = pd.concat([existing, df], ignore_index=True)
        merged = merged.drop_duplicates(subset=["地区", "日期"], keep="last")
        merged.to_csv(output_path, index=False, encoding="utf-8-sig")
        new_count = len(merged) - len(existing)
        print(f"[*] Saved to {output_path} ({len(merged)} total, {max(0, new_count)} new)")
    else:
        df.to_csv(output_path, index=False, encoding="utf-8-sig")
        print(f"[*] Saved to {output_path} ({len(df)} rows)")


def save_to_db(rows):
    """Append rows to MySQL records table."""
    try:
        from dotenv import load_dotenv
        load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))
    except ImportError:
        pass

    host = os.getenv("MYSQL_HOST")
    if not host:
        print("[!] MYSQL_HOST not configured, skipping DB save")
        return

    from sqlalchemy import create_engine, text
    port = int(os.getenv("MYSQL_PORT", "3306"))
    user = os.getenv("MYSQL_USER", "root")
    pw = os.getenv("MYSQL_PASSWORD", "")
    db = os.getenv("MYSQL_DATABASE", "air_quality")
    url = f"mysql+pymysql://{user}:{pw}@{host}:{port}/{db}?charset=utf8mb4"

    engine = create_engine(url, pool_pre_ping=True)
    # Deduplicate: delete existing rows with same (city, date) then insert
    with engine.begin() as conn:
        for row in rows:
            conn.execute(
                text("DELETE FROM records WHERE city=:city AND date=:date"),
                {"city": row["地区"], "date": row["日期"]},
            )

    records = []
    for row in rows:
        records.append({
            "city": row["地区"],
            "date": row["日期"],
            "quality_level": row["质量等级"],
            "aqi": row["AQI指数"],
            "aqi_rank": row["当天AQI排名"],
            "pm25": row["PM2.5"],
            "pm10": row["PM10"],
            "so2": row["So2"],
            "no2": row["No2"],
            "co": row["Co"],
            "o3": row["O3"],
            "year": row["年份"],
            "month": row["月份"],
            "season": row["季节"],
            "level_code": row["等级编码"],
        })

    df = pd.DataFrame(records)
    df.to_sql("records", engine, if_exists="append", index=False,
              chunksize=1000, method="multi")
    print(f"[*] Saved {len(records)} rows to MySQL records table")


def main():
    parser = argparse.ArgumentParser(description="CNEMC Air Quality Scraper")
    parser.add_argument("--output", "-o", default=None,
                        help="CSV output path (default: ../cnemc_data_<date>.csv)")
    parser.add_argument("--to-db", action="store_true",
                        help="Save to MySQL records table")
    parser.add_argument("--interval", type=int, default=0,
                        help="Run every N seconds (daemon mode)")
    parser.add_argument("--max-workers", type=int, default=MAX_WORKERS,
                        help=f"Concurrent workers (default: {MAX_WORKERS})")
    parser.add_argument("--cities", nargs="*", default=None,
                        help="Specific city names to scrape (for testing)")
    args = parser.parse_args()

    tz_beijing = timezone(timedelta(hours=8))

    while True:
        print(f"\n{'='*60}")
        print(f"[*] CNEMC Scraper — {datetime.now(tz_beijing).strftime('%Y-%m-%d %H:%M:%S')} (CST)")
        print(f"{'='*60}")

        if args.cities:
            cities = [(0, c) for c in args.cities]
        else:
            cities = get_all_cities()

        if not cities:
            print("[!] No cities found")
            if args.interval == 0:
                sys.exit(1)
            time.sleep(args.interval)
            continue

        rows = scrape_all_cities(cities, max_workers=args.max_workers)

        if not rows:
            print("[!] No data scraped")
            if args.interval == 0:
                sys.exit(1)
            time.sleep(args.interval)
            continue

        if args.output:
            csv_path = args.output
        else:
            date_tag = rows[0]["日期"]
            csv_path = os.path.join(
                os.path.dirname(os.path.dirname(__file__)),
                f"cnemc_data_{date_tag}.csv",
            )

        save_to_csv(rows, csv_path)

        if args.to_db:
            save_to_db(rows)

        if args.interval == 0:
            break

        print(f"[*] Next run in {args.interval}s ...")
        time.sleep(args.interval)


if __name__ == "__main__":
    main()
