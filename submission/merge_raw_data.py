"""Merge all raw city CSV files into a single dataset and generate stats."""
import csv, os, sys
from collections import Counter

# Ensure UTF-8 output
sys.stdout.reconfigure(encoding='utf-8')

RAW_DIR = 'D:/Desktop/作业/数据可视化/爬虫数据（部分原始数据)'
OUT_DIR = os.path.dirname(os.path.abspath(__file__))

def detect_encoding(fpath):
    """Try UTF-8 first, fall back to GBK."""
    for enc in ['utf-8', 'gbk', 'gb18030']:
        try:
            with open(fpath, 'r', encoding=enc) as f:
                next(csv.reader(f))
            return enc
        except (UnicodeDecodeError, StopIteration):
            continue
    return 'latin-1'

def read_csv_safe(fpath, encoding):
    """Read CSV with given encoding, return (header, rows)."""
    with open(fpath, 'r', encoding=encoding) as f:
        reader = csv.reader(f)
        try:
            header = next(reader)
        except StopIteration:
            return None, []
        rows = [row for row in reader if row and any(c.strip() for c in row)]
    return header, rows

# ============================================================
# STEP 1: Merge all files
# ============================================================
files = sorted([f for f in os.listdir(RAW_DIR) if f.endswith('.csv')])
print(f"Found {len(files)} city CSV files")

all_rows = []
total_days = 0
enc_counts = Counter()
city_date_ranges = {}

for fname in files:
    fpath = os.path.join(RAW_DIR, fname)
    city = fname.replace('.csv', '')
    enc = detect_encoding(fpath)
    enc_counts[enc] += 1

    header, rows = read_csv_safe(fpath, enc)
    if header is None:
        print(f"  SKIP empty file: {fname}")
        continue
    # header: 日期, 质量等级, AQI指数, 当天AQI排名, PM2.5, PM10, So2, No2, Co, O3
    # Add city column at position 0
    for row in rows:
        row.insert(0, city)
        all_rows.append(row)
    total_days += len(rows)

    if rows:
        city_date_ranges[city] = (len(rows), rows[0][1], rows[-1][1])

print(f"Encoding: {dict(enc_counts)}")
print(f"Total rows: {total_days}")
print(f"Cities: {len(files)}")

# Write merged file
merged_path = os.path.join(OUT_DIR, '原始数据集.csv')
new_header = ['地区', '日期', '质量等级', 'AQI指数', '当天AQI排名', 'PM2.5', 'PM10', 'So2', 'No2', 'Co', 'O3']
with open(merged_path, 'w', encoding='utf-8-sig', newline='') as f:
    writer = csv.writer(f)
    writer.writerow(new_header)
    writer.writerows(all_rows)

file_size_mb = os.path.getsize(merged_path) / (1024 * 1024)
print(f"Merged file: {merged_path} ({file_size_mb:.1f} MB)")

# ============================================================
# STEP 2: Data profiling stats
# ============================================================
print("\n=== DATA PROFILING ===")

# Date range
dates = [row[1] for row in all_rows]
# Normalize date format (some use /, some use -)
dates_sorted = sorted(set(dates))
print(f"Date range: {dates_sorted[0]} ~ {dates_sorted[-1]}")
print(f"Unique dates: {len(dates_sorted)}")

# Quality level distribution
quality_levels = Counter(row[2] for row in all_rows)
print(f"\nQuality distribution:")
for q, cnt in quality_levels.most_common():
    pct = cnt / total_days * 100
    print(f"  {q}: {cnt} ({pct:.1f}%)")

# Numeric columns: AQI(3), PM2.5(5), PM10(6), SO2(7), NO2(8), CO(9), O3(10)
import numpy as np

numeric_cols = {
    'AQI指数': 3,
    'PM2.5': 5,
    'PM10': 6,
    'So2': 7,
    'No2': 8,
    'Co': 9,
    'O3': 10,
}

for name, idx in numeric_cols.items():
    vals = []
    for row in all_rows:
        try:
            v = float(row[idx])
            vals.append(v)
        except (ValueError, IndexError):
            pass
    if vals:
        arr = np.array(vals)
        print(f"\n{name}: n={len(arr)}, mean={arr.mean():.2f}, std={arr.std():.2f}, "
              f"min={arr.min():.2f}, max={arr.max():.2f}, "
              f"p25={np.percentile(arr,25):.1f}, p50={np.percentile(arr,50):.1f}, p75={np.percentile(arr,75):.1f}")
        # Outliers
        q1, q3 = np.percentile(arr, 25), np.percentile(arr, 75)
        iqr = q3 - q1
        outliers = arr[(arr < q1 - 1.5*iqr) | (arr > q3 + 1.5*iqr)]
        print(f"  Outliers (1.5*IQR): {len(outliers)} ({len(outliers)/len(arr)*100:.2f}%)")

# City data completeness
print(f"\nCity data completeness:")
city_counts = Counter(row[0] for row in all_rows)
sorted_cities = city_counts.most_common()
print(f"  Top 5: {sorted_cities[:5]}")
print(f"  Bottom 5: {sorted_cities[-5:]}")
print(f"  Mean days/city: {np.mean([c for _,c in sorted_cities]):.0f}")
print(f"  Median days/city: {np.median([c for _,c in sorted_cities]):.0f}")

# Year/season analysis
year_counts = Counter()
for row in all_rows:
    date_str = row[1]
    # Handle both date formats
    for sep in ['-', '/']:
        if sep in date_str:
            parts = date_str.split(sep)
            if len(parts) >= 1:
                year = parts[0]
                year_counts[year] += 1
            break

print(f"\nYear distribution:")
for yr in sorted(year_counts.keys()):
    print(f"  {yr}: {year_counts[yr]} rows")

# Missing values check
print(f"\nMissing value check:")
for col_name in new_header:
    col_idx = new_header.index(col_name)
    missing = sum(1 for row in all_rows if col_idx >= len(row) or row[col_idx].strip() == '' or row[col_idx].strip() == 'NA')
    print(f"  {col_name}: {missing} missing ({missing/total_days*100:.2f}%)")

print("\nDone.")
