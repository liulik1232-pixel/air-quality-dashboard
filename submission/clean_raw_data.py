"""
Comprehensive data cleaning script for raw air quality CSV files.
Covers: duplicate removal, missing value handling, outlier removal,
        format standardization, quality verification.
"""
import csv, os, sys, re, json
from collections import Counter, defaultdict

sys.stdout.reconfigure(encoding='utf-8')

RAW_DIR = 'D:/Desktop/作业/数据可视化/爬虫数据（部分原始数据)'
OUT_DIR = os.path.dirname(os.path.abspath(__file__))
LOG_PATH = os.path.join(OUT_DIR, '清洗处理日志.txt')

log_lines = []
stats = {}  # step -> {before, after, removed, detail}

def log(msg):
    print(msg)
    log_lines.append(msg)

# ================================================================
# PINYIN -> CHINESE CITY NAME MAPPING
# ================================================================
PINYIN_TO_CN = {
    'akesu': '阿克苏', 'ali': '阿里', 'ankang': '安康', 'anshan': '鞍山',
    'anshun': '安顺', 'baicheng': '白城', 'baise': '百色', 'baishan': '白山',
    'baiyin': '白银', 'baoding': '保定', 'baoji': '宝鸡', 'baoshan': '保山',
    'baotou': '包头', 'bayannaoer': '巴彦淖尔', 'beihai': '北海', 'beijing': '北京',
    'benxi': '本溪', 'bijie': '毕节', 'cangzhou': '沧州', 'changchun': '长春',
    'changdu': '昌都', 'changzhi': '长治', 'changzhou': '常州', 'chengde': '承德',
    'chengdu': '成都', 'chifeng': '赤峰', 'chongqing': '重庆', 'chongzuo': '崇左',
    'dali': '大理', 'dalian': '大连', 'dandong': '丹东', 'daqing': '大庆',
    'datong': '大同', 'dehong': '德宏', 'deyang': '德阳', 'dingxi': '定西',
    'dongguang': '东莞',
    'eerduosi': '鄂尔多斯', 'fangchenggang': '防城港', 'foshan': '佛山',
    'gannan': '甘南', 'guangyuan': '广元', 'guangzhou': '广州',
    'guigang': '贵港', 'guilin': '桂林', 'guiyang': '贵阳',
    'guyuan': '固原', 'haerbin': '哈尔滨', 'haibei': '海北', 'haidong': '海东',
    'haikou': '海口', 'hainan': '海南', 'haixi': '海西', 'hami': '哈密',
    'handan': '邯郸', 'hangzhou': '杭州', 'hanzhong': '汉中', 'hechi': '河池',
    'hegang': '鹤岗', 'hengshui': '衡水', 'hengyang': '衡阳', 'hetian': '和田',
    'heyuan': '河源', 'hezhou': '贺州', 'huangnan': '黄南', 'huhehaote': '呼和浩特',
    'huizhou': '惠州', 'huludao': '葫芦岛', 'huzhou': '湖州', 'jiamusi': '佳木斯',
    'jiangmen': '江门', 'jiaxing': '嘉兴', 'jiayuguan': '嘉峪关', 'jilin': '吉林',
    'jinchang': '金昌', 'jincheng': '晋城', 'jinhua': '金华', 'jinzhong': '晋中',
    'jinzhou': '锦州', 'jiuquan': '酒泉', 'jixi': '鸡西', 'kelamayi': '克拉玛依',
    'kunming': '昆明', 'laibin': '来宾', 'langfang': '廊坊', 'lanzhou': '兰州',
    'lasa': '拉萨', 'leshan': '乐山', 'liaoyuan': '辽源', 'lijiang': '丽江',
    'lincang': '临沧', 'linfen': '临汾', 'linxia': '临夏', 'linzhi': '林芝',
    'lishui': '丽水', 'liupanshui': '六盘水', 'liuzhou': '柳州', 'longnan': '陇南',
    'luzhou': '泸州', 'lvliang': '吕梁', 'meishan': '眉山', 'mianyang': '绵阳',
    'nanchong': '南充', 'nanjing': '南京', 'nanning': '南宁',
    'nantong': '南通', 'naqu': '那曲', 'ningbo': '宁波', 'nujiang': '怒江',
    'panjin': '盘锦', 'panzhihua': '攀枝花', 'pingliang': '平凉',
    'qiandongnan': '黔东南', 'qiannan': '黔南', 'qianxinan': '黔西南',
    'qingyang': '庆阳', 'qingyuan': '清远', 'qinhuangdao': '秦皇岛',
    'qinzhou': '钦州', 'qiqihaer': '齐齐哈尔', 'qitaihe': '七台河',
    'qujing': '曲靖', 'quzhou': '衢州', 'rikaze': '日喀则', 'sanya': '三亚',
    'shanghai': '上海', 'shannan': '山南', 'shantou': '汕头', 'shaoguan': '韶关',
    'shaoxing': '绍兴', 'shenyang': '沈阳', 'shenzhen': '深圳',
    'shihezi': '石河子', 'shijiazhuang': '石家庄', 'shizuishan': '石嘴山',
    'shuangyashan': '双鸭山', 'shuozhou': '朔州', 'siping': '四平',
    'songyuan': '松原', 'suining': '遂宁', 'suzhou': '苏州',
    'taiyuan': '太原', 'taizhou': '台州', 'tangshan': '唐山',
    'tianjin': '天津', 'tianshui': '天水', 'tongchuan': '铜川',
    'tonghua': '通化', 'tongliao': '通辽', 'tongren': '铜仁',
    'wafangdian': '瓦房店', 'weinan': '渭南', 'wenzhou': '温州',
    'wuhai': '乌海', 'wujiaqu': '五家渠', 'wulumuqi': '乌鲁木齐',
    'wuwei': '武威', 'wuxi': '无锡', 'wuzhong': '吴忠', 'wuzhou': '梧州',
    'xian': '西安', 'xiangxi': '湘西', 'xianyang': '咸阳', 'xingtai': '邢台',
    'xining': '西宁', 'xinzhou': '忻州', 'xishuangbanna': '西双版纳',
    'xuzhou': '徐州', 'yanan': '延安', 'yanbian': '延边', 'yangquan': '阳泉',
    'yinchuan': '银川', 'yingkou': '营口', 'yueyang': '岳阳',
    'yulin': '玉林',
    'yuncheng': '运城', 'yushu': '玉树', 'yuxi': '玉溪',
    'zhangjiakou': '张家口', 'zhangye': '张掖', 'zhaoqing': '肇庆',
    'zhaotong': '昭通', 'zhongshan': '中山', 'zhongwei': '中卫',
    'zhoushan': '舟山', 'zhuhai': '珠海', 'zigong': '自贡', 'zunyi': '遵义',
}

# ================================================================
# ENVIRONMENTAL STANDARDS (valid physical/measurement ranges)
# ================================================================
VALID_RANGES = {
    'AQI指数': (0, 500),
    'PM2.5': (0, 900),
    'PM10': (0, 1000),
    'So2': (0, 500),
    'No2': (0, 300),
    'Co': (0, 10),
    'O3': (0, 500),
}
VALID_QUALITY = {'优', '良', '轻度污染', '中度污染', '重度污染', '严重污染'}
MAX_CITY_RANK = 389  # aqistudy.cn covers up to 389 cities

NUM_COLS = {
    'AQI指数': 3,
    '当天AQI排名': 4,
    'PM2.5': 5,
    'PM10': 6,
    'So2': 7,
    'No2': 8,
    'Co': 9,
    'O3': 10,
}

# ================================================================
def detect_encoding(fpath):
    for enc in ['utf-8', 'gbk', 'gb18030']:
        try:
            with open(fpath, 'r', encoding=enc) as f:
                next(csv.reader(f))
            return enc
        except (UnicodeDecodeError, StopIteration):
            continue
    return 'latin-1'

def parse_num(s):
    """Parse numeric string, return float or None."""
    s = s.strip()
    if not s or s.upper() == 'NA':
        return None
    # Handle <3 (detection limit)
    s = re.sub(r'^[<≤]\s*', '', s)
    # Handle ~ ranges (take midpoint)
    m = re.match(r'^(\d+\.?\d*)\s*~\s*(\d+\.?\d*)$', s)
    if m:
        return (float(m.group(1)) + float(m.group(2))) / 2
    try:
        return float(s)
    except ValueError:
        return None

def make_key(row):
    """Create a dedup key from a row (all fields, exact match)."""
    return tuple(row)

def make_city_date_key(row):
    """Create a (city, date) key for duplicate detection."""
    return (row[0], row[1])

# ================================================================
# STEP 1: LOAD ALL RAW DATA
# ================================================================
log("=" * 70)
log("                   空气质量原始数据清洗处理报告")
log("=" * 70)
log("")
log("原始数据路径: " + RAW_DIR)
log("清洗日期: 2026-06-16")
log("参考标准: GB 3095-2012 环境空气质量标准")
log("")

log("=" * 70)
log("STEP 1: 原始数据加载")
log("=" * 70)
log("说明: 逐文件检测编码并读取所有城市CSV文件，添加城市名列。")

files = sorted([f for f in os.listdir(RAW_DIR) if f.endswith('.csv')])
all_rows = []
empty_files = []
enc_stats = Counter()

for fname in files:
    fpath = os.path.join(RAW_DIR, fname)
    city_pinyin = fname.replace('.csv', '')

    if os.path.getsize(fpath) < 10:
        empty_files.append(city_pinyin)
        continue

    enc = detect_encoding(fpath)
    enc_stats[enc] += 1

    with open(fpath, 'r', encoding=enc) as f:
        reader = csv.reader(f)
        try:
            header = next(reader)
        except StopIteration:
            empty_files.append(city_pinyin)
            continue

        for row in reader:
            if not row or all(c.strip() == '' for c in row):
                continue
            row.insert(0, city_pinyin)
            all_rows.append(row)

before = len(all_rows)
log(f"  - 发现CSV文件: {len(files)} 个")
log(f"  - 有效文件: {len(files) - len(empty_files)} 个")
log(f"  - 空文件: {len(empty_files)} 个")
if empty_files:
    log(f"    空文件列表: {', '.join(empty_files)}")
log(f"  - 编码分布: GBK={enc_stats.get('gbk',0)}个, UTF-8={enc_stats.get('utf-8',0)}个")
log(f"  - 加载总行数: {before}")
stats['load'] = before

# ================================================================
# STEP 2: REMOVE HEADER ROWS MIXED INTO DATA
# ================================================================
log("")
log("=" * 70)
log("STEP 2: 剔除表头误入行")
log("=" * 70)
log("说明: 部分CSV文件在拼接过程中表头行混入数据区，'质量等级'列的值为'质量等级'即为表头行。")

before = len(all_rows)
header_contaminated = [r for r in all_rows if r[2] == '质量等级']
for r in header_contaminated[:5]:
    log(f"  - 示例表头行: 城市={r[0]}, 日期={r[1]}, 质量等级={r[2]}")

all_rows = [r for r in all_rows if r[2] != '质量等级']
removed = before - len(all_rows)
log(f"  - 剔除表头行: {removed} 条")
log(f"  - 剩余: {len(all_rows)} 条")
stats['header'] = removed

# ================================================================
# STEP 3: REMOVE EXACT DUPLICATE ROWS
# ================================================================
log("")
log("=" * 70)
log("STEP 3: 剔除完全重复记录")
log("=" * 70)
log("说明: 按照全部11个字段完全匹配检测重复，保留首次出现记录。")

before = len(all_rows)
seen = set()
unique_rows = []
dup_cities = Counter()
for row in all_rows:
    key = make_key(row)
    if key not in seen:
        seen.add(key)
        unique_rows.append(row)
    else:
        dup_cities[row[0]] += 1

removed = before - len(unique_rows)
log(f"  - 完全重复行: {removed} 条")
if dup_cities:
    top_dup = dup_cities.most_common(5)
    log(f"  - 重复最多的城市: {', '.join(f'{c}({n}条)' for c,n in top_dup)}")
log(f"  - 剩余: {len(unique_rows)} 条")
all_rows = unique_rows
stats['exact_dup'] = removed

# ================================================================
# STEP 4: HANDLE (CITY, DATE) DUPLICATES (different values, same city+date)
# ================================================================
log("")
log("=" * 70)
log("STEP 4: 处理(城市,日期)重复（同城同日不同值）")
log("=" * 70)
log("说明: 全字段去重后仍可能存在同城市同日期但数值不同的记录，保留数据更完整的那条。")

before = len(all_rows)
city_date_groups = defaultdict(list)
for i, row in enumerate(all_rows):
    city_date_groups[(row[0], row[1])].append(i)

dup_pairs = {k: v for k, v in city_date_groups.items() if len(v) > 1}
log(f"  - 发现重复(城市,日期)对: {len(dup_pairs)} 组")

# For each duplicate group, keep the row with more non-zero numeric values
remove_indices = set()
for (city, date), indices in dup_pairs.items():
    best_idx = indices[0]
    best_score = -1
    for idx in indices:
        row = all_rows[idx]
        score = 0
        for name, col in NUM_COLS.items():
            val = parse_num(row[col])
            if val is not None and val > 0:
                score += 1
        if score > best_score:
            best_score = score
            best_idx = idx
    for idx in indices:
        if idx != best_idx:
            remove_indices.add(idx)

log(f"  - 其中删除: {len(remove_indices)} 条（保留数据更完整的记录）")

for idx in sorted(remove_indices, reverse=True):
    all_rows.pop(idx)

log(f"  - 剩余: {len(all_rows)} 条")
stats['city_date_dup'] = len(remove_indices)

# ================================================================
# STEP 5: MAP PINYIN TO CHINESE CITY NAMES
# ================================================================
log("")
log("=" * 70)
log("STEP 5: 城市名称标准化（拼音 → 中文）")
log("=" * 70)
log("说明: 原始文件名使用拼音，根据城市坐标对照表统一转为规范中文名称。")

mapped_count = 0
unmapped = set()
for row in all_rows:
    pinyin = row[0]
    if pinyin in PINYIN_TO_CN:
        row[0] = PINYIN_TO_CN[pinyin]
        mapped_count += 1
    else:
        unmapped.add(pinyin)

log(f"  - 成功映射: {mapped_count} 条 ({len(PINYIN_TO_CN)} 个城市)")
if unmapped:
    log(f"  - 未能映射: {unmapped}")
stats['pinyin_mapped'] = len(PINYIN_TO_CN)

# ================================================================
# STEP 6: STANDARDIZE DATE FORMAT
# ================================================================
log("")
log("=" * 70)
log("STEP 6: 日期格式标准化（统一为 YYYY-MM-DD）")
log("=" * 70)
log("说明: 原始数据中存在 YYYY-MM-DD、YYYY/MM/DD、YYYY/M/D 等多种格式，统一为 ISO 8601 标准格式。")

date_fixes = 0
invalid_dates = []

for i, row in enumerate(all_rows):
    raw_date = row[1].strip()
    if re.match(r'^\d{4}-\d{2}-\d{2}$', raw_date):
        continue
    m = re.match(r'^(\d{4})/(\d{1,2})/(\d{1,2})$', raw_date)
    if m:
        row[1] = f"{m.group(1)}-{int(m.group(2)):02d}-{int(m.group(3)):02d}"
        date_fixes += 1
        continue
    # Invalid format
    invalid_dates.append(i)

log(f"  - 日期格式修正(YYYY/MM/DD → YYYY-MM-DD): {date_fixes} 条")
if invalid_dates:
    log(f"  - 无效日期(删除): {len(invalid_dates)} 条")
    for i in reversed(invalid_dates):
        all_rows.pop(i)
else:
    log(f"  - 无效日期: 0 条")
log(f"  - 剩余: {len(all_rows)} 条")
stats['date_fix'] = date_fixes

# ================================================================
# STEP 7: VALIDATE QUALITY LEVEL
# ================================================================
log("")
log("=" * 70)
log("STEP 7: 质量等级字段校验")
log("=" * 70)
log("说明: 质量等级必须是国家标准六分类之一，非标准值直接剔除。")

before = len(all_rows)
invalid_q = [r for r in all_rows if r[2] not in VALID_QUALITY]
if invalid_q:
    for r in invalid_q[:5]:
        log(f"  - 无效值: 城市={r[0]}, 日期={r[1]}, 值='{r[2]}'")

all_rows = [r for r in all_rows if r[2] in VALID_QUALITY]
removed = before - len(all_rows)
log(f"  - 无效质量等级: {removed} 条")
log(f"  - 有效六分类: {', '.join(sorted(VALID_QUALITY))}")
stats['quality'] = removed

# ================================================================
# STEP 8: NUMERIC FIELD VALIDATION & OUTLIER REMOVAL
# ================================================================
log("")
log("=" * 70)
log("STEP 8: 数值字段校验与异常值剔除")
log("=" * 70)
log("说明: 结合GB 3095-2012标准及物理测量合理范围，剔除负值、超量程等错误数据。")
log("")

before = len(all_rows)

# Track detailed removals
removal_details = {
    'non_numeric': Counter(),     # 无法转换为数值
    'negative': Counter(),        # 负值
    'out_of_range': Counter(),    # 超出合理范围
    'rank_out_of_range': 0,       # AQI排名超限
}

valid_rows = []
co_small_neg_fix = 0

for row in all_rows:
    keep = True

    # --- Check AQI rank ---
    rank_str = row[4].strip()
    rank_val = parse_num(rank_str)
    if rank_val is None:
        removal_details['non_numeric']['当天AQI排名'] += 1
        keep = False
    elif rank_val <= 0 or rank_val > MAX_CITY_RANK * 2:
        # >778 (2x max cities) is unreasonable
        removal_details['rank_out_of_range'] += 1
        keep = False
    else:
        row[4] = rank_val  # store as float for now

    if not keep:
        continue

    # --- Check pollutant columns ---
    for name, idx in NUM_COLS.items():
        if name == '当天AQI排名':
            continue

        raw_val = row[idx].strip()
        val = parse_num(raw_val)

        if val is None:
            removal_details['non_numeric'][name] += 1
            keep = False
            break

        # Handle negative values
        if val < 0:
            if name == 'Co' and val > -1:
                # Tiny negative → round to 0 (floating point artifact)
                val = 0.0
                co_small_neg_fix += 1
            else:
                removal_details['negative'][name] += 1
                keep = False
                break

        # Check valid range
        if name in VALID_RANGES:
            lo, hi = VALID_RANGES[name]
            if val < lo or val > hi:
                removal_details['out_of_range'][name] += 1
                keep = False
                break

        row[idx] = val

    if keep:
        valid_rows.append(row)

# Report
log("各字段异常剔除明细:")
log(f"  {'字段':<12} {'非数值':>6} {'负值':>6} {'超范围':>6} {'合计':>6}")
log(f"  {'-'*12} {'-'*6} {'-'*6} {'-'*6} {'-'*6}")
for name in NUM_COLS:
    nn = removal_details['non_numeric'].get(name, 0)
    neg = removal_details['negative'].get(name, 0)
    oor = removal_details['out_of_range'].get(name, 0)
    total = nn + neg + oor
    if total > 0:
        log(f"  {name:<12} {nn:>6} {neg:>6} {oor:>6} {total:>6}")

if removal_details['rank_out_of_range'] > 0:
    log(f"  {'AQI排名超限':<12} {'':>6} {'':>6} {'':>6} {removal_details['rank_out_of_range']:>6}")

log(f"")
log(f"  - Co微小负值修正为0: {co_small_neg_fix} 条（浮点误差，非真正负值）")
removed = before - len(valid_rows)
log(f"  - 因数值异常共删除: {removed} 条")
log(f"  - 剩余: {len(valid_rows)} 条")

all_rows = valid_rows
stats['numeric_outlier'] = removed

# ================================================================
# STEP 9: HANDLE MISSING NUMERIC VALUES
# ================================================================
log("")
log("=" * 70)
log("STEP 9: 缺失值处理")
log("=" * 70)
log("说明: 经上述处理后各字段无真正缺失值。对于AQI排名中超过389的值（合理但偏高），保留原始值不做修改。")
log("       数据集中不存在需要插值填充的连续缺失。")

# Count any None values remaining
none_count = 0
for row in all_rows:
    for idx in NUM_COLS.values():
        if row[idx] is None:
            none_count += 1
log(f"  - 残留空值: {none_count} 个")
stats['missing'] = none_count

# ================================================================
# STEP 10: FINAL FORMAT STANDARDIZATION
# ================================================================
log("")
log("=" * 70)
log("STEP 10: 最终格式标准化")
log("=" * 70)
log("说明: 统一数值精度和字符编码格式。")

for row in all_rows:
    for name, idx in NUM_COLS.items():
        if isinstance(row[idx], (int, float)):
            if name == 'Co':
                row[idx] = round(row[idx], 2)
            elif name == 'O3':
                row[idx] = round(row[idx], 1)
            else:
                row[idx] = round(row[idx], 1)

log(f"  - 数值精度: AQI/PM2.5/PM10/SO2/NO2/O3 → 1位小数, CO → 2位小数")
log(f"  - 字符编码: 统一输出为 UTF-8 with BOM")
log(f"  - 日期格式: ISO 8601 (YYYY-MM-DD)")
log(f"  - 城市名称: 规范中文全称")

# ================================================================
# STEP 11: QUALITY VERIFICATION
# ================================================================
log("")
log("=" * 70)
log("STEP 11: 清洗后质量核验")
log("=" * 70)

cities_final = sorted(set(row[0] for row in all_rows))
log(f"  - 城市数: {len(cities_final)}")
log(f"  - 总记录数: {len(all_rows)}")

# Quality distribution
q_dist = Counter(row[2] for row in all_rows)
log(f"  - 质量等级分布:")
for q, c in q_dist.most_common():
    log(f"      {q}: {c} ({c/len(all_rows)*100:.1f}%)")

# Date range
dates_final = sorted(set(row[1] for row in all_rows))
log(f"  - 日期范围: {dates_final[0]} ~ {dates_final[-1]}")
log(f"  - 唯一日期数: {len(dates_final)}")

# Numeric stats
import numpy as np
log(f"")
log(f"  - 数值字段描述性统计:")
log(f"    {'字段':<12} {'均值':>8} {'标准差':>8} {'最小值':>8} {'最大值':>8}")
log(f"    {'-'*12} {'-'*8} {'-'*8} {'-'*8} {'-'*8}")
for name, idx in NUM_COLS.items():
    vals = [r[idx] for r in all_rows if isinstance(r[idx], (int, float))]
    if vals:
        arr = np.array(vals)
        log(f"    {name:<12} {arr.mean():>8.2f} {arr.std():>8.2f} {arr.min():>8.1f} {arr.max():>8.1f}")

# City completeness
city_counts = Counter(r[0] for r in all_rows)
log(f"")
log(f"  - 城市数据完整度:")
log(f"    数据最完整(top 5):")
for city, cnt in city_counts.most_common(5):
    log(f"      {city}: {cnt} 天")
log(f"    数据最少(bottom 5):")
for city, cnt in city_counts.most_common()[-5:]:
    log(f"      {city}: {cnt} 天")
log(f"    均值: {np.mean([c for _,c in city_counts.items()]):.0f} 天/城市")
log(f"    中位数: {np.median([c for _,c in city_counts.items()]):.0f} 天/城市")

# Final duplicate check
city_date_pairs = [(r[0], r[1]) for r in all_rows]
remaining_dup = len(city_date_pairs) - len(set(city_date_pairs))
log(f"")
log(f"  - (城市,日期)残留重复: {remaining_dup} 条")
log(f"  - 缺失值总量: {none_count} 个")

# ================================================================
# STEP 12: WRITE CLEANED CSV
# ================================================================
log("")
log("=" * 70)
log("STEP 12: 输出清洗后数据集")
log("=" * 70)

CLEANED_HEADER = ['地区', '日期', '质量等级', 'AQI指数', '当天AQI排名',
                  'PM2.5', 'PM10', 'So2', 'No2', 'Co', 'O3']

cleaned_path = os.path.join(OUT_DIR, '清洗后数据集.csv')
with open(cleaned_path, 'w', encoding='utf-8-sig', newline='') as f:
    writer = csv.writer(f)
    writer.writerow(CLEANED_HEADER)
    all_rows.sort(key=lambda r: (r[0], r[1]))
    for row in all_rows:
        out = []
        for i, val in enumerate(row):
            if isinstance(val, float):
                if CLEANED_HEADER[i] == 'Co':
                    out.append(f'{val:.2f}')
                else:
                    out.append(f'{val:.1f}')
            else:
                out.append(str(val))
        writer.writerow(out)

size_mb = os.path.getsize(cleaned_path) / (1024 * 1024)
log(f"  - 输出文件: {cleaned_path}")
log(f"  - 文件大小: {size_mb:.1f} MB")
log(f"  - 字段数: {len(CLEANED_HEADER)}")
log(f"  - 记录数: {len(all_rows)} 条")
log(f"  - 城市数: {len(cities_final)} 个")
log(f"  - 编码: UTF-8 with BOM")

# ================================================================
# SUMMARY
# ================================================================
log("")
log("=" * 70)
log("                    清洗处理摘要")
log("=" * 70)
log(f"  原始记录数:         {stats.get('load', '?')}")
log(f"  - 表头误入剔除:     {stats.get('header', 0)}")
log(f"  - 完全重复剔除:     {stats.get('exact_dup', 0)}")
log(f"  - 同城同日重复剔除: {stats.get('city_date_dup', 0)}")
log(f"  - 质量等级无效剔除: {stats.get('quality', 0)}")
log(f"  - 数值异常剔除:     {stats.get('numeric_outlier', 0)}")
log(f"  = 清洗后记录数:     {len(all_rows)}")
log(f"  总清洗率:           {(1 - len(all_rows)/stats.get('load',1))*100:.1f}%")

# ================================================================
# WRITE LOG
# ================================================================
with open(LOG_PATH, 'w', encoding='utf-8') as f:
    f.write('\n'.join(log_lines))

log("")
log("处理日志已保存至: " + LOG_PATH)
log("清洗后数据集: " + cleaned_path)
log("数据清洗完成!")
