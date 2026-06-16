"""
AQI Study History Data Scraper (aqistudy.cn)
Uses Playwright for JS crypto + Python requests for HTTP.

The site uses custom Base64 + DES + AES encryption that's difficult to
replicate in pure Python. Instead, we use the browser's JS functions to
encrypt/decrypt, and Python's requests for reliable HTTP.

Usage:
  python aqistudy_scraper.py --city 北京 --start 202401
  python aqistudy_scraper.py --start 201312  # all cities, all years
  python aqistudy_scraper.py --test
"""
import argparse
import json
import os
import sys
import time
from datetime import datetime

import pandas as pd
import requests
import urllib3
from playwright.sync_api import sync_playwright

urllib3.disable_warnings()

# ── Constants ──────────────────────────────────────────────────
BASE_URL = "https://www.aqistudy.cn/historydata"
API_URL = f"{BASE_URL}/api/historyapi.php"
DAYDATA_URL = f"{BASE_URL}/daydata.php"

CSV_COLUMNS = [
    "地区", "日期", "质量等级", "AQI指数", "当天AQI排名",
    "PM2.5", "PM10", "So2", "No2", "Co", "O3",
    "年份", "月份", "季节", "等级编码",
]
QUALITY_MAP = {"优": 1, "良": 2, "轻度污染": 3, "中度污染": 4, "重度污染": 5, "严重污染": 6}
SEASON_MAP = {3: "春", 4: "春", 5: "春", 6: "夏", 7: "夏", 8: "夏",
              9: "秋", 10: "秋", 11: "秋", 12: "冬", 1: "冬", 2: "冬"}

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/plain, */*; q=0.01",
    "Accept-Language": "zh-CN,zh;q=0.9",
    "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
    "X-Requested-With": "XMLHttpRequest",
    "Origin": BASE_URL,
    "Referer": f"{BASE_URL}/",
}


def _gen_months(start_ym, end_ym):
    sy, sm = int(start_ym[:4]), int(start_ym[4:6])
    ey, em = int(end_ym[:4]), int(end_ym[4:6])
    months = []
    y, m = sy, sm
    while y < ey or (y == ey and m <= em):
        months.append(f"{y}{m:02d}")
        m += 1
        if m > 12:
            m = 1
            y += 1
    return months


class AqiStudyScraper:
    def __init__(self, headless=True):
        self.headless = headless
        self._playwright = None
        self._browser = None
        self._page = None
        self._http = requests.Session()
        self._http.headers.update(HEADERS)
        self._http.verify = False

    def start(self):
        self._playwright = sync_playwright().start()
        self._browser = self._playwright.chromium.launch(
            headless=self.headless,
            args=[
                "--ignore-certificate-errors",
                "--disable-blink-features=AutomationControlled",
            ],
        )
        ctx = self._browser.new_context(ignore_https_errors=True)
        self._page = ctx.new_page()
        self._page.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', { get: () => false });
            window.chrome = { runtime: {} };
            Object.defineProperty(navigator, 'plugins', { get: () => [1, 2, 3, 4, 5] });
            Object.defineProperty(navigator, 'languages', { get: () => ['zh-CN', 'zh'] });
        """)

    def _init_crypto(self):
        """Load daydata.php to initialize JS crypto functions. Retry on timeout."""
        for attempt in range(5):
            try:
                print(f"    Loading crypto (attempt {attempt + 1})...")
                self._page.goto(
                    f"{DAYDATA_URL}?city=北京&month=202401",
                    wait_until="domcontentloaded",
                    timeout=60000,
                )
                self._page.wait_for_function(
                    "typeof poPBVxzNuafY8Yu === 'function'",
                    timeout=30000,
                )
                # Test it works
                test = self._page.evaluate(
                    "poPBVxzNuafY8Yu('GETDAYDATA', {city:'北京',month:'202401'})"
                )
                if test and len(test) > 50:
                    print("    Crypto ready [OK]")
                    return True
            except Exception as e:
                msg = str(e)[:100]
                print(f"    Attempt {attempt + 1} failed: {msg}")
                if attempt < 4:
                    time.sleep(5)
        return False

    def encrypt_request(self, method, params):
        """Use browser JS to encrypt API request."""
        for attempt in range(3):
            try:
                encrypted = self._page.evaluate(
                    "([m, p]) => poPBVxzNuafY8Yu(m, p)",
                    [method, params],
                )
                if encrypted:
                    return encrypted
            except Exception as e:
                if attempt < 2:
                    self._init_crypto()
                else:
                    raise
        return None

    def decrypt_response(self, data):
        """Use browser JS to decrypt API response."""
        return self._page.evaluate("(d) => dxvERkeEvHbS(d)", data)

    def get_city_list(self):
        """Fetch all city names from the site."""
        resp = self._http.get(
            f"{BASE_URL}/monthdata.php",
            headers={"User-Agent": HEADERS["User-Agent"]},
            timeout=30,
        )
        resp.encoding = "utf-8"
        cities = set()
        import re
        for m in re.finditer(r'monthdata\.php\?city=([^"&\047]+)', resp.text):
            cities.add(m.group(1))
        for m in re.finditer(r'daydata\.php\?city=([^"&\047]+)', resp.text):
            cities.add(m.group(1))
        return sorted(cities)

    def fetch_daily_data(self, city, month_ym):
        """Fetch daily data for one city-month."""
        encrypted = self._page.evaluate(
            "(p) => poPBVxzNuafY8Yu('GETDAYDATA', p)",
            {"city": city, "month": month_ym},
        )
        resp = self._http.post(API_URL, data={"hA4Nse2cT": encrypted}, timeout=60)
        resp.raise_for_status()
        decrypted = self._page.evaluate("(d) => dxvERkeEvHbS(d)", resp.text)
        data = json.loads(decrypted)
        if not data.get("success"):
            return []
        result = data.get("result", {})
        if not result.get("success"):
            return []
        items = result.get("data", {}).get("items", [])
        return self._parse(items, city, month_ym)

    def _parse(self, items, city, month_ym):
        year = int(month_ym[:4])
        month = int(month_ym[4:6])
        rows = []
        for item in items:
            ts = item.get("time_point", "")
            if not ts:
                continue
            try:
                aqi = float(item.get("aqi", 0))
                pm25 = float(item.get("pm2_5", 0))
                pm10 = float(item.get("pm10", 0))
                so2 = float(item.get("so2", 0))
                no2 = float(item.get("no2", 0))
                co = float(item.get("co", 0))
                o3 = float(item.get("o3", 0))
            except (ValueError, TypeError):
                continue
            quality = item.get("quality", "") or self._aqi_to_quality(aqi)
            rows.append({
                "地区": city, "日期": ts, "质量等级": quality,
                "AQI指数": aqi, "当天AQI排名": None,
                "PM2.5": pm25, "PM10": pm10, "So2": so2,
                "No2": no2, "Co": co, "O3": o3,
                "年份": year, "月份": month,
                "季节": SEASON_MAP.get(month, ""),
                "等级编码": QUALITY_MAP.get(quality, 0),
            })
        return rows

    @staticmethod
    def _aqi_to_quality(aqi):
        if aqi <= 50: return "优"
        elif aqi <= 100: return "良"
        elif aqi <= 150: return "轻度污染"
        elif aqi <= 200: return "中度污染"
        elif aqi <= 300: return "重度污染"
        return "严重污染"

    def close(self):
        if self._browser:
            self._browser.close()
        if self._playwright:
            self._playwright.stop()


def main():
    # Force UTF-8 output on Windows
    if sys.platform == "win32":
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    parser = argparse.ArgumentParser()
    parser.add_argument("--city", default=None)
    parser.add_argument("--start", default="201312")
    parser.add_argument("--end", default=None)
    parser.add_argument("--output", "-o", default=None)
    parser.add_argument("--test", action="store_true")
    parser.add_argument("--visible", action="store_true")
    parser.add_argument("--delay", type=float, default=0.3)
    args = parser.parse_args()

    if args.end is None:
        args.end = datetime.now().strftime("%Y%m")

    months = _gen_months(args.start, args.end)

    scraper = AqiStudyScraper(headless=not args.visible)
    try:
        scraper.start()
        if not scraper._init_crypto():
            print("[!] Failed to initialize crypto")
            return

        if args.city:
            cities = [args.city]
        else:
            print("[*] Loading city list...")
            cities = scraper.get_city_list()
            print(f"[*] Found {len(cities)} cities")

        if args.test:
            months = months[:2]
            if not args.city:
                cities = cities[:3]

        print(f"[*] Target: {len(cities)} cities x {len(months)} months")

        all_rows = []
        done = 0
        total = len(cities) * len(months)

        for city in cities:
            for month_ym in months:
                done += 1
                print(f"  [{done}/{total}] {city} {month_ym} ...", end=" ", flush=True)
                try:
                    rows = scraper.fetch_daily_data(city, month_ym)
                    all_rows.extend(rows)
                    print(f"{len(rows)} days")
                except Exception as e:
                    print(f"ERR: {e}")
                time.sleep(args.delay)

        if not all_rows:
            print("[!] No data scraped")
            return

        df = pd.DataFrame(all_rows, columns=CSV_COLUMNS).fillna(0)
        for date, group in df.groupby("日期"):
            df.loc[group.index, "当天AQI排名"] = (
                group["AQI指数"].rank(method="min", ascending=True).astype(int)
            )

        path = args.output or f"aqistudy_{args.start}_{args.end}.csv"
        df.to_csv(path, index=False, encoding="utf-8-sig")
        print(f"\n[*] {len(df)} rows -> {path}")
        print(f"    {df['地区'].nunique()} cities, {df['日期'].min()} ~ {df['日期'].max()}")
    finally:
        scraper.close()


if __name__ == "__main__":
    main()
