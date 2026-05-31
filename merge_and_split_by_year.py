"""merge_and_split_by_year.py — 合并所有城市预处理文件 → 全国数据集 + 按年拆分"""
import os
import pandas as pd

PROCESSED_DIR = "processed_data"
OUTPUT_DIR = "yearly_data"

os.makedirs(OUTPUT_DIR, exist_ok=True)

files = [f for f in os.listdir(PROCESSED_DIR) if f.endswith('_preprocessed.csv')]
print(f"找到 {len(files)} 个预处理文件")

all_data = []
city_count = 0

for fname in files:
    city_name = fname.replace('_preprocessed.csv', '')
    fpath = os.path.join(PROCESSED_DIR, fname)

    df = pd.read_csv(fpath, encoding='utf-8-sig', parse_dates=['日期'], low_memory=False)
    df['地区'] = city_name

    all_data.append(df)
    city_count += 1
    print(f"  {city_name}: {len(df)} 条")

if not all_data:
    print("没有有效数据，请检查 processed_data 中的文件")
    exit(1)

merged = pd.concat(all_data, ignore_index=True)
print(f"\n合并完成: {len(merged):,} 条记录, {city_count} 个城市")

# Clean: remove rows with missing key fields
merged = merged.dropna(subset=['日期', '质量等级', 'AQI指数'])
# Remove duplicate date+city rows (keep first)
merged = merged.drop_duplicates(subset=['地区', '日期'], keep='first')

# Ensure correct column order
cols = ['地区', '日期', '质量等级', 'AQI指数', '当天AQI排名',
        'PM2.5', 'PM10', 'So2', 'No2', 'Co', 'O3',
        '年份', '月份', '季节', '等级编码']
merged = merged[[c for c in cols if c in merged.columns]]

# Ensure numeric types are clean
for col in ['AQI指数', 'PM2.5', 'PM10', 'So2', 'No2', 'Co', 'O3']:
    merged[col] = pd.to_numeric(merged[col], errors='coerce')
merged['年份'] = merged['年份'].astype(int)
merged['月份'] = merged['月份'].astype(int)
merged['等级编码'] = merged['等级编码'].astype(int)

# Save merged
merged_path = 'all_cities_all_years.csv'
merged.to_csv(merged_path, index=False, encoding='utf-8-sig')
print(f"全国数据集: {merged_path} ({len(merged):,} 行)")

# Split by year
years = sorted(merged['年份'].unique())
for yr in years:
    ydf = merged[merged['年份'] == yr]
    yr_path = os.path.join(OUTPUT_DIR, f"{int(yr)}.csv")
    ydf.to_csv(yr_path, index=False, encoding='utf-8-sig')
    print(f"  {int(yr)}年: {len(ydf):,} 条 → {yr_path}")

print(f"\n完成。数据年份: {years[0]} - {years[-1]}")
