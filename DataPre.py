"""DataPre.py — 原始城市CSV清洗 → 标准化预处理文件"""
import os
import re
import pandas as pd

INPUT_DIR = "raw_data"
OUTPUT_DIR = "processed_data"

QUALITY_LEVELS = ['优', '良', '轻度污染', '中度污染', '重度污染', '严重污染']
LEVEL_MAP = {name: i + 1 for i, name in enumerate(QUALITY_LEVELS)}

SEASON_MAP = {
    3: '春', 4: '春', 5: '春',
    6: '夏', 7: '夏', 8: '夏',
    9: '秋', 10: '秋', 11: '秋',
    12: '冬', 1: '冬', 2: '冬',
}

os.makedirs(OUTPUT_DIR, exist_ok=True)

files = [f for f in os.listdir(INPUT_DIR) if f.endswith('.csv')]
print(f"找到 {len(files)} 个原始文件")

for fname in files:
    city_name = fname.replace('.csv', '')
    fpath = os.path.join(INPUT_DIR, fname)

    try:
        df = pd.read_csv(fpath, encoding='utf-8-sig')
    except Exception:
        try:
            df = pd.read_csv(fpath, encoding='gbk')
        except Exception as e:
            print(f"  [跳过] {city_name}: 无法解析 ({e})")
            continue

    if df.empty or len(df.columns) < 2:
        print(f"  [跳过] {city_name}: 空文件或列数不足")
        continue

    # Normalize: some files have no header for column 0, some use '/' dates
    cols = list(df.columns)
    if cols[0] != '日期':
        # First column is date but unlabeled
        df.columns = ['日期'] + cols[1:]

    # Normalize date format (handle both 2013/10/28 and 2013-10-28)
    df['日期'] = pd.to_datetime(df['日期'].astype(str).str.replace('/', '-'), errors='coerce')
    df = df.dropna(subset=['日期'])

    # Extract temporal fields
    df['年份'] = df['日期'].dt.year
    df['月份'] = df['日期'].dt.month
    df['季节'] = df['月份'].map(SEASON_MAP)

    # Map quality level to encoding
    df['等级编码'] = df['质量等级'].map(LEVEL_MAP)

    # Drop rows with missing quality level
    df = df.dropna(subset=['等级编码'])
    df['等级编码'] = df['等级编码'].astype(int)

    # Ensure numeric columns are clean
    for col in ['AQI指数', '当天AQI排名', 'PM2.5', 'PM10', 'So2', 'No2', 'Co', 'O3']:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors='coerce')

    # Select and order standard columns
    out_cols = ['日期', '质量等级', 'AQI指数', '当天AQI排名',
                'PM2.5', 'PM10', 'So2', 'No2', 'Co', 'O3',
                '年份', '月份', '季节', '等级编码']
    df = df[[c for c in out_cols if c in df.columns]]

    out_path = os.path.join(OUTPUT_DIR, f"{city_name}_preprocessed.csv")
    df.to_csv(out_path, index=False, encoding='utf-8-sig')
    print(f"  {city_name}: {len(df)} 条 → {out_path}")

print(f"\n完成，输出到 {OUTPUT_DIR}/")
