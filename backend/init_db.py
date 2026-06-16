"""Initialize MySQL database for Air Quality Smart Dashboard.

Phases:
  1. CREATE DATABASE (utf8mb4)
  2. DROP + CREATE all tables (records, cities, 17 aggregation tables)
  3. Import CSV → `records` table (584,504 rows)
  4. Import city coords + region map → `cities` table
  5. Compute ALL aggregations (pandas once) → 17 materialized tables

Usage:
    python init_db.py            # full init
    python init_db.py --keep     # skip data load, only ensure schema
    python init_db.py --agg-only # only recompute aggregation tables (records+cities must exist)
"""
import argparse
import json
import os
import sys
import time

import numpy as np
import pandas as pd
import pymysql
from dotenv import load_dotenv
from sqlalchemy import create_engine, text

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from data_loader import (  # noqa: E402
    REGION_MAP, QUALITY_LEVELS, POLLUTANTS, CORRELATION_VARS,
    MONTH_NAMES, SEASONS,
)

load_dotenv(os.path.join(os.path.dirname(__file__), '.env'))

MYSQL_HOST = os.getenv('MYSQL_HOST', 'localhost')
MYSQL_PORT = int(os.getenv('MYSQL_PORT', '3306'))
MYSQL_USER = os.getenv('MYSQL_USER', 'root')
MYSQL_PASSWORD = os.getenv('MYSQL_PASSWORD', '')
MYSQL_DATABASE = os.getenv('MYSQL_DATABASE', 'air_quality')

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CSV_PATH = os.path.join(BASE_DIR, 'all_cities_all_years.csv')
COORDS_PATH = os.path.join(os.path.dirname(__file__), 'city_coords.json')


def make_db_url():
    return (f"mysql+pymysql://{MYSQL_USER}:{MYSQL_PASSWORD}"
            f"@{MYSQL_HOST}:{MYSQL_PORT}/{MYSQL_DATABASE}?charset=utf8mb4")


def ensure_database():
    conn = pymysql.connect(host=MYSQL_HOST, port=MYSQL_PORT,
                           user=MYSQL_USER, password=MYSQL_PASSWORD,
                           charset='utf8mb4')
    try:
        with conn.cursor() as cur:
            cur.execute(
                f"CREATE DATABASE IF NOT EXISTS `{MYSQL_DATABASE}` "
                "CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"
            )
        conn.commit()
        print(f"[InitDB] Database `{MYSQL_DATABASE}` ready.")
    finally:
        conn.close()


# ── DDL constants ──────────────────────────────────────────────

SCHEMA_RECORDS = """
CREATE TABLE IF NOT EXISTS records (
    id          BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY,
    city        VARCHAR(64)  NOT NULL,
    date        DATE         NOT NULL,
    quality_level VARCHAR(16),
    aqi         FLOAT,
    aqi_rank    FLOAT,
    pm25        FLOAT,
    pm10        FLOAT,
    so2         FLOAT,
    no2         FLOAT,
    co          FLOAT,
    o3          FLOAT,
    year        SMALLINT     NOT NULL,
    month       TINYINT      NOT NULL,
    season      VARCHAR(4),
    level_code  TINYINT,
    KEY idx_city_date (city, date),
    KEY idx_year_month (year, month),
    KEY idx_city_year (city, year),
    KEY idx_date (date)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 DEFAULT CHARSET=utf8mb4
"""

SCHEMA_CITIES = """
CREATE TABLE IF NOT EXISTS cities (
    name    VARCHAR(64)  NOT NULL PRIMARY KEY,
    region  VARCHAR(16),
    lng     DOUBLE,
    lat     DOUBLE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 DEFAULT CHARSET=utf8mb4
"""

# Aggregation tables (materialized from pandas precompute)
AGG_DDL = {
    "yearly_agg": """
        CREATE TABLE IF NOT EXISTS yearly_agg (
            year       SMALLINT NOT NULL PRIMARY KEY,
            avg_aqi    FLOAT,   median_aqi FLOAT,  aqi_std FLOAT,
            total_days INT,     city_count INT
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """,
    "monthly_agg": """
        CREATE TABLE IF NOT EXISTS monthly_agg (
            year SMALLINT NOT NULL,  month TINYINT NOT NULL,
            avg_aqi FLOAT,  min_aqi FLOAT,  max_aqi FLOAT,
            avg_pm25 FLOAT, avg_pm10 FLOAT, avg_so2 FLOAT,
            avg_no2 FLOAT,  avg_co FLOAT,   avg_o3 FLOAT,
            PRIMARY KEY (year, month)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """,
    "seasonal_agg": """
        CREATE TABLE IF NOT EXISTS seasonal_agg (
            year   SMALLINT NOT NULL,  season VARCHAR(4) NOT NULL,
            avg_aqi  FLOAT, avg_pm25 FLOAT, avg_pm10 FLOAT,
            avg_so2  FLOAT, avg_no2  FLOAT, avg_co  FLOAT, avg_o3 FLOAT,
            PRIMARY KEY (year, season)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """,
    "city_seasonal_agg": """
        CREATE TABLE IF NOT EXISTS city_seasonal_agg (
            year   SMALLINT NOT NULL,  city VARCHAR(64) NOT NULL,  season VARCHAR(4) NOT NULL,
            avg_aqi  FLOAT, avg_pm25 FLOAT, avg_pm10 FLOAT,
            avg_so2  FLOAT, avg_no2  FLOAT, avg_co  FLOAT, avg_o3 FLOAT,
            PRIMARY KEY (year, city, season)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """,
    "city_yearly": """
        CREATE TABLE IF NOT EXISTS city_yearly (
            year     SMALLINT NOT NULL,  city VARCHAR(64) NOT NULL,
            avg_aqi  FLOAT, avg_pm25 FLOAT, avg_pm10 FLOAT,
            avg_so2  FLOAT, avg_no2  FLOAT, avg_co  FLOAT, avg_o3 FLOAT,
            days     INT,
            PRIMARY KEY (year, city)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """,
    "city_quality_dist": """
        CREATE TABLE IF NOT EXISTS city_quality_dist (
            year SMALLINT NOT NULL,  city VARCHAR(64) NOT NULL,
            quality_level VARCHAR(16) NOT NULL,  cnt INT,
            PRIMARY KEY (year, city, quality_level)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """,
    "city_monthly_agg": """
        CREATE TABLE IF NOT EXISTS city_monthly_agg (
            year SMALLINT NOT NULL,  month TINYINT NOT NULL,  city VARCHAR(64) NOT NULL,
            avg_aqi FLOAT,  min_aqi FLOAT,  max_aqi FLOAT,
            avg_pm25 FLOAT, avg_pm10 FLOAT, day_count INT,
            PRIMARY KEY (year, month, city)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """,
    "daily_national": """
        CREATE TABLE IF NOT EXISTS daily_national (
            date    DATE NOT NULL PRIMARY KEY,
            avg_aqi FLOAT
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """,
    "quality_dist_yearly": """
        CREATE TABLE IF NOT EXISTS quality_dist_yearly (
            year SMALLINT NOT NULL,  quality_level VARCHAR(16) NOT NULL,
            cnt INT,  pct FLOAT,
            PRIMARY KEY (year, quality_level)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """,
    "good_ratio_yearly": """
        CREATE TABLE IF NOT EXISTS good_ratio_yearly (
            year SMALLINT NOT NULL,  city VARCHAR(64) NOT NULL,
            pct FLOAT,
            PRIMARY KEY (year, city)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """,
    "heavy_pollution_yearly": """
        CREATE TABLE IF NOT EXISTS heavy_pollution_yearly (
            year SMALLINT NOT NULL,  city VARCHAR(64) NOT NULL,
            cnt INT,  pct FLOAT,
            PRIMARY KEY (year, city)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """,
    "primary_pollutant_yearly": """
        CREATE TABLE IF NOT EXISTS primary_pollutant_yearly (
            year SMALLINT NOT NULL,  city VARCHAR(64) NOT NULL,
            pollutant VARCHAR(16),
            PRIMARY KEY (year, city)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """,
    "pm_ratio_yearly": """
        CREATE TABLE IF NOT EXISTS pm_ratio_yearly (
            year SMALLINT NOT NULL,  city VARCHAR(64) NOT NULL,
            ratio FLOAT,
            PRIMARY KEY (year, city)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """,
    "correlation_yearly": """
        CREATE TABLE IF NOT EXISTS correlation_yearly (
            year        SMALLINT NOT NULL PRIMARY KEY,
            labels_json TEXT,
            matrix_json MEDIUMTEXT
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """,
    "pollution_episodes": """
        CREATE TABLE IF NOT EXISTS pollution_episodes (
            id         BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY,
            year       SMALLINT NOT NULL,
            city       VARCHAR(64),
            start_date DATE,
            end_date   DATE,
            duration   INT,
            max_aqi    FLOAT,
            avg_aqi    FLOAT,
            KEY idx_ep_year (year)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """,
    "heatmap_yearly": """
        CREATE TABLE IF NOT EXISTS heatmap_yearly (
            year       SMALLINT NOT NULL PRIMARY KEY,
            cities_json MEDIUMTEXT,
            months_json TEXT,
            data_json   MEDIUMTEXT
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """,
    "level_transitions_yearly": """
        CREATE TABLE IF NOT EXISTS level_transitions_yearly (
            year       SMALLINT NOT NULL PRIMARY KEY,
            labels_json TEXT,
            matrix_json MEDIUMTEXT
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """,
    "pollutant_composition_yearly": """
        CREATE TABLE IF NOT EXISTS pollutant_composition_yearly (
            year     SMALLINT NOT NULL,  pollutant VARCHAR(16) NOT NULL,
            avg_val  FLOAT,  max_val FLOAT,  min_val FLOAT,  std_val FLOAT,
            PRIMARY KEY (year, pollutant)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """,
    "clusters_yearly": """
        CREATE TABLE IF NOT EXISTS clusters_yearly (
            year       SMALLINT NOT NULL,
            cluster_id TINYINT NOT NULL,
            cities_json MEDIUMTEXT,
            cnt        INT,
            avg_aqi    FLOAT,
            PRIMARY KEY (year, cluster_id)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """,
    "similarity_yearly": """
        CREATE TABLE IF NOT EXISTS similarity_yearly (
            id       BIGINT AUTO_INCREMENT PRIMARY KEY,
            year     SMALLINT NOT NULL,
            city1    VARCHAR(64),
            city2    VARCHAR(64),
            distance FLOAT,
            KEY idx_sim_year (year)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """,
}


def ensure_schema(engine, drop=False, agg_only=False):
    with engine.begin() as conn:
        if drop:
            if not agg_only:
                conn.execute(text("DROP TABLE IF EXISTS records"))
                conn.execute(text("DROP TABLE IF EXISTS cities"))
                print("[InitDB] Dropped existing tables.")
            for name in AGG_DDL:
                conn.execute(text(f"DROP TABLE IF EXISTS {name}"))
            print("[InitDB] All aggregation tables dropped and recreated.")
        if not agg_only:
            conn.execute(text(SCHEMA_RECORDS))
            conn.execute(text(SCHEMA_CITIES))
            print("[InitDB] Schema ensured (records, cities).")
        for name, ddl in AGG_DDL.items():
            conn.execute(text(ddl))
    print(f"[InitDB] Schema ensured ({'all' if not agg_only else f'{len(AGG_DDL)} agg'} tables).")


def load_records(engine):
    print(f"[InitDB] Reading CSV: {CSV_PATH}")
    t0 = time.time()
    df = pd.read_csv(CSV_PATH, encoding='utf-8-sig', low_memory=False)
    df['日期'] = pd.to_datetime(df['日期'], errors='coerce')
    df = df.dropna(subset=['日期'])
    print(f"[InitDB] Parsed {len(df):,} rows in {time.time()-t0:.1f}s")
    df = df.rename(columns={
        '地区': 'city', '日期': 'date', '质量等级': 'quality_level',
        'AQI指数': 'aqi', '当天AQI排名': 'aqi_rank',
        'PM2.5': 'pm25', 'PM10': 'pm10',
        'So2': 'so2', 'No2': 'no2', 'Co': 'co', 'O3': 'o3',
        '年份': 'year', '月份': 'month', '季节': 'season', '等级编码': 'level_code',
    })
    df = df[['city', 'date', 'quality_level', 'aqi', 'aqi_rank',
             'pm25', 'pm10', 'so2', 'no2', 'co', 'o3',
             'year', 'month', 'season', 'level_code']]
    print(f"[InitDB] Inserting {len(df):,} rows into `records` ...")
    t0 = time.time()
    df.to_sql('records', engine, if_exists='append', index=False,
              chunksize=5000, method='multi')
    print(f"[InitDB] records done in {time.time()-t0:.1f}s")


def load_cities(engine):
    with open(COORDS_PATH, 'r', encoding='utf-8') as f:
        coords = json.load(f)
    city_region = {}
    for region, cities_list in REGION_MAP.items():
        for c in cities_list:
            city_region[c] = region
    rows = []
    for city, lnglat in coords.items():
        lng, lat = lnglat[0], lnglat[1]
        rows.append({
            'name': city,
            'region': city_region.get(city, '其他'),
            'lng': lng, 'lat': lat,
        })
    cdf = pd.DataFrame(rows)
    cdf.to_sql('cities', engine, if_exists='append', index=False,
               chunksize=500, method='multi')
    print(f"[InitDB] cities done ({len(cdf)} rows).")


def _bulk_insert(engine, table, rows, chunk=2000):
    """Insert list-of-dict rows into `table`."""
    if not rows:
        print(f"  [skip] {table}: 0 rows")
        return
    df = pd.DataFrame(rows)
    df.to_sql(table, engine, if_exists='append', index=False,
              chunksize=chunk, method='multi')
    print(f"  {table}: {len(df):,} rows")


def compute_aggregations(engine):
    """Use the existing AirQualityDataLoader (CSV mode) to precompute everything,
    then dump every _xxx dict into the matching aggregation table."""
    print("[InitDB] Computing aggregations (pandas) ...")
    t0 = time.time()

    # Force CSV mode — temporarily remove MYSQL_HOST so the loader falls back
    old_host = os.environ.pop('MYSQL_HOST', None)
    try:
        from data_loader import AirQualityDataLoader
        loader = AirQualityDataLoader(CSV_PATH, COORDS_PATH)
    finally:
        if old_host is not None:
            os.environ['MYSQL_HOST'] = old_host

    print(f"[InitDB] Precompute done in {time.time()-t0:.1f}s. Writing to MySQL ...")
    t1 = time.time()

    # ── yearly_agg ──
    _bulk_insert(engine, 'yearly_agg', [
        {'year': int(yr), 'avg_aqi': v['avg_aqi'], 'median_aqi': v['median_aqi'],
         'aqi_std': v['aqi_std'], 'total_days': v['total_days'], 'city_count': v['city_count']}
        for yr, v in loader._yearly.items()
    ])

    # ── monthly_agg ──
    _bulk_insert(engine, 'monthly_agg', [
        {'year': int(yr), 'month': int(mo), **d}
        for yr, md in loader._monthly.items()
        for mo, d in md.items()
    ])

    # ── seasonal_agg ──
    _bulk_insert(engine, 'seasonal_agg', [
        {'year': int(yr), 'season': s, **d}
        for yr, sd in loader._seasonal.items()
        for s, d in sd.items()
    ])

    # ── city_seasonal_agg ──
    city_seasonal_rows = []
    for yr, cd in loader._city_seasonal.items():
        for city, sd in cd.items():
            for s, d in sd.items():
                city_seasonal_rows.append({
                    'year': int(yr), 'city': city, 'season': s,
                    **d
                })
    _bulk_insert(engine, 'city_seasonal_agg', city_seasonal_rows)

    # ── city_yearly + city_quality_dist ──
    cy_rows, cqd_rows = [], []
    for yr, cd in loader._city_yearly.items():
        for city, d in cd.items():
            cy_rows.append({
                'year': int(yr), 'city': city,
                'avg_aqi': d['avg_aqi'], 'avg_pm25': d['avg_pm25'],
                'avg_pm10': d['avg_pm10'], 'avg_so2': d['avg_so2'],
                'avg_no2': d['avg_no2'], 'avg_co': d['avg_co'],
                'avg_o3': d['avg_o3'], 'days': d['days'],
            })
            for lvl, cnt in d.get('quality_dist', {}).items():
                cqd_rows.append({'year': int(yr), 'city': city,
                                 'quality_level': lvl, 'cnt': int(cnt)})
    _bulk_insert(engine, 'city_yearly', cy_rows)
    _bulk_insert(engine, 'city_quality_dist', cqd_rows)

    # ── city_monthly_agg ──
    cm_rows = []
    for yr in loader.years:
        cdf_all = loader.df[loader.df['年份'] == yr]
        for city in loader.cities:
            cdf = cdf_all[cdf_all['地区'] == city]
            if len(cdf) == 0:
                continue
            for mo in range(1, 13):
                mdf = cdf[cdf['月份'] == mo]
                if len(mdf) > 0:
                    cm_rows.append({
                        'year': int(yr), 'month': int(mo), 'city': city,
                        'avg_aqi': round(float(mdf['AQI指数'].mean()), 2),
                        'min_aqi': round(float(mdf['AQI指数'].min()), 2),
                        'max_aqi': round(float(mdf['AQI指数'].max()), 2),
                        'avg_pm25': round(float(mdf['PM2.5'].mean()), 2),
                        'avg_pm10': round(float(mdf['PM10'].mean()), 2),
                        'day_count': len(mdf),
                    })
    _bulk_insert(engine, 'city_monthly_agg', cm_rows)

    # ── daily_national ──
    daily = loader._moving_avg['daily']
    _bulk_insert(engine, 'daily_national', [
        {'date': str(d.date()), 'avg_aqi': round(float(v), 2)}
        for d, v in daily.items()
    ])

    # ── quality_dist_yearly ──
    _bulk_insert(engine, 'quality_dist_yearly', [
        {'year': int(yr), 'quality_level': lvl,
         'cnt': d['count'], 'pct': d['pct']}
        for yr, ld in loader._quality_dist.items()
        for lvl, d in ld.items()
    ])

    # ── good_ratio_yearly ──
    _bulk_insert(engine, 'good_ratio_yearly', [
        {'year': int(yr), 'city': c, 'pct': pct}
        for yr, cd in loader._good_ratio.items()
        for c, pct in cd.items()
    ])

    # ── heavy_pollution_yearly ──
    _bulk_insert(engine, 'heavy_pollution_yearly', [
        {'year': int(yr), 'city': c, 'cnt': d['count'], 'pct': d['pct']}
        for yr, cd in loader._heavy_pollution.items()
        for c, d in cd.items()
    ])

    # ── primary_pollutant_yearly ──
    _bulk_insert(engine, 'primary_pollutant_yearly', [
        {'year': int(yr), 'city': c, 'pollutant': pol}
        for yr, cd in loader._primary_pollutant.items()
        for c, pol in cd.items()
    ])

    # ── pm_ratio_yearly ──
    _bulk_insert(engine, 'pm_ratio_yearly', [
        {'year': int(yr), 'city': c, 'ratio': r}
        for yr, cd in loader._pm_ratio.items()
        for c, r in cd.items()
    ])

    # ── correlation_yearly (JSON) ──
    _bulk_insert(engine, 'correlation_yearly', [
        {'year': int(yr), 'labels_json': json.dumps(d['labels']),
         'matrix_json': json.dumps(d['matrix'])}
        for yr, d in loader._correlations.items()
    ])

    # ── pollution_episodes ──
    ep_rows = []
    for yr, eps in loader._episodes.items():
        for ep in eps:
            ep_rows.append({
                'year': int(yr), 'city': ep['city'],
                'start_date': ep['start_date'], 'end_date': ep['end_date'],
                'duration': ep['duration'], 'max_aqi': ep['max_aqi'],
                'avg_aqi': ep['avg_aqi'],
            })
    _bulk_insert(engine, 'pollution_episodes', ep_rows)

    # ── heatmap_yearly (JSON) ──
    _bulk_insert(engine, 'heatmap_yearly', [
        {'year': int(yr), 'cities_json': json.dumps(d['cities']),
         'months_json': json.dumps(d['months']), 'data_json': json.dumps(d['data'])}
        for yr, d in loader._heatmap.items()
    ])

    # ── level_transitions_yearly (JSON) ──
    _bulk_insert(engine, 'level_transitions_yearly', [
        {'year': int(yr), 'labels_json': json.dumps(d['labels']),
         'matrix_json': json.dumps(d['matrix'])}
        for yr, d in loader._level_transitions.items()
    ])

    # ── pollutant_composition_yearly ──
    pc_rows = []
    for yr, pdict in loader._pollutant_composition.items():
        for pol, d in pdict.items():
            pc_rows.append({
                'year': int(yr), 'pollutant': pol,
                'avg_val': d['avg'], 'max_val': d['max'],
                'min_val': d['min'], 'std_val': d['std'],
            })
    _bulk_insert(engine, 'pollutant_composition_yearly', pc_rows)

    # ── clusters_yearly ──
    cl_rows = []
    for yr, cdict in loader._clusters.items():
        for cid, cdata in cdict.items():
            cl_rows.append({
                'year': int(yr), 'cluster_id': int(cid),
                'cities_json': json.dumps(cdata['cities']),
                'cnt': cdata['count'], 'avg_aqi': cdata['avg_aqi'],
            })
    _bulk_insert(engine, 'clusters_yearly', cl_rows)

    # ── similarity_yearly ──
    sim_rows = []
    for yr, pairs in loader._similarity.items():
        for p in pairs:
            sim_rows.append({
                'year': int(yr), 'city1': p['city1'],
                'city2': p['city2'], 'distance': p['distance'],
            })
    _bulk_insert(engine, 'similarity_yearly', sim_rows)

    print(f"[InitDB] All aggregation tables written in {time.time()-t1:.1f}s")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--keep', action='store_true',
                        help='Skip data load; only ensure schema exists.')
    parser.add_argument('--agg-only', action='store_true',
                        help='Only recompute aggregation tables (records+cities must exist).')
    args = parser.parse_args()

    if not args.agg_only:
        if not os.path.exists(CSV_PATH):
            print(f"[InitDB] CSV not found: {CSV_PATH}", file=sys.stderr)
            sys.exit(1)
        if not os.path.exists(COORDS_PATH):
            print(f"[InitDB] Coords not found: {COORDS_PATH}", file=sys.stderr)
            sys.exit(1)

    ensure_database()
    engine = create_engine(make_db_url(), pool_pre_ping=True)

    if args.agg_only:
        ensure_schema(engine, drop=True, agg_only=True)
        compute_aggregations(engine)
        print("[InitDB] --agg-only complete.")
        return

    ensure_schema(engine, drop=not args.keep)

    if args.keep:
        print("[InitDB] --keep set, skipping data load.")
        return

    load_records(engine)
    load_cities(engine)
    compute_aggregations(engine)
    print("[InitDB] All done.")


if __name__ == '__main__':
    main()
