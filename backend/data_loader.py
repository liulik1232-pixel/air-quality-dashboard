"""Air Quality Data Loader — 一次性加载CSV并预计算所有聚合维度。"""
import json
import os
import numpy as np
import pandas as pd
from collections import defaultdict
from sklearn.cluster import KMeans
from sklearn.preprocessing import StandardScaler
from scipy.spatial.distance import pdist, squareform
from scipy import stats as sp_stats


QUALITY_LEVELS = ['优', '良', '轻度污染', '中度污染', '重度污染', '严重污染']
QUALITY_COLORS = ['#2ecc71', '#3498db', '#f1c40f', '#e67e22', '#e74c3c', '#8b0000']
POLLUTANTS = ['PM2.5', 'PM10', 'So2', 'No2', 'Co', 'O3']
CORRELATION_VARS = ['PM2.5', 'PM10', 'So2', 'No2', 'Co', 'O3', 'AQI指数']
MONTH_NAMES = ['1月', '2月', '3月', '4月', '5月', '6月', '7月', '8月', '9月', '10月', '11月', '12月']
SEASONS = ['春', '夏', '秋', '冬']

# 七大区域划分
REGION_MAP = {
    '华北': ['北京', '天津', '石家庄', '唐山', '秦皇岛', '邯郸', '邢台', '保定', '张家口', '承德', '沧州', '廊坊', '衡水', '太原', '大同', '阳泉', '长治', '晋城', '朔州', '忻州', '吕梁', '晋中', '临汾', '运城', '呼和浩特', '包头', '乌海', '赤峰', '通辽', '鄂尔多斯', '呼伦贝尔', '巴彦淖尔', '乌兰察布', '兴安', '锡林郭勒', '阿拉善', '五家渠', '石河子'],
    '东北': ['沈阳', '大连', '鞍山', '抚顺', '本溪', '丹东', '锦州', '营口', '阜新', '辽阳', '盘锦', '铁岭', '朝阳', '葫芦岛', '长春', '吉林', '四平', '辽源', '通化', '白山', '松原', '白城', '延边', '哈尔滨', '齐齐哈尔', '鸡西', '鹤岗', '双鸭山', '大庆', '伊春', '佳木斯', '七台河', '牡丹江', '黑河', '绥化', '大兴安岭', '瓦房店', '东光'],
    '华东': ['上海', '南京', '无锡', '徐州', '常州', '苏州', '南通', '连云港', '淮安', '盐城', '扬州', '镇江', '泰州', '宿迁', '杭州', '宁波', '温州', '嘉兴', '湖州', '绍兴', '金华', '衢州', '舟山', '台州', '丽水', '合肥', '芜湖', '蚌埠', '淮南', '马鞍山', '淮北', '铜陵', '安庆', '黄山', '滁州', '阜阳', '宿州', '六安', '亳州', '池州', '宣城', '巢湖', '南昌', '景德镇', '萍乡', '九江', '新余', '鹰潭', '赣州', '吉安', '宜春', '抚州', '上饶', '济南', '青岛', '淄博', '枣庄', '东营', '烟台', '潍坊', '济宁', '泰安', '威海', '日照', '临沂', '德州', '聊城', '滨州', '菏泽', '莱芜', '福州', '厦门', '莆田', '三明', '泉州', '漳州', '南平', '龙岩', '宁德'],
    '华中': ['郑州', '开封', '洛阳', '平顶山', '安阳', '鹤壁', '新乡', '焦作', '濮阳', '许昌', '漯河', '三门峡', '南阳', '商丘', '信阳', '周口', '驻马店', '济源', '武汉', '黄石', '十堰', '宜昌', '襄阳', '鄂州', '荆门', '孝感', '荆州', '黄冈', '咸宁', '随州', '恩施', '长沙', '株洲', '湘潭', '衡阳', '邵阳', '岳阳', '常德', '张家界', '益阳', '郴州', '永州', '怀化', '娄底', '湘西'],
    '华南': ['广州', '韶关', '深圳', '珠海', '汕头', '佛山', '江门', '湛江', '茂名', '肇庆', '惠州', '梅州', '汕尾', '河源', '清远', '东莞', '中山', '潮州', '揭阳', '云浮', '阳江', '南宁', '柳州', '桂林', '梧州', '北海', '防城港', '钦州', '贵港', '玉林', '百色', '贺州', '河池', '来宾', '崇左', '海口', '三亚', '五指山', '琼海', '儋州', '文昌', '万宁', '东方', '定安'],
    '西南': ['重庆', '成都', '自贡', '攀枝花', '泸州', '德阳', '绵阳', '广元', '遂宁', '内江', '乐山', '南充', '眉山', '宜宾', '广安', '达州', '雅安', '巴中', '资阳', '阿坝', '甘孜', '凉山', '贵阳', '六盘水', '遵义', '安顺', '毕节', '铜仁', '黔西南', '黔东南', '黔南', '昆明', '曲靖', '玉溪', '保山', '昭通', '丽江', '普洱', '临沧', '楚雄', '红河', '文山', '西双版纳', '大理', '德宏', '怒江', '迪庆', '拉萨', '昌都', '山南', '日喀则', '那曲', '阿里', '林芝'],
    '西北': ['西安', '铜川', '宝鸡', '咸阳', '渭南', '延安', '汉中', '榆林', '安康', '商洛', '兰州', '嘉峪关', '金昌', '白银', '天水', '武威', '张掖', '平凉', '酒泉', '庆阳', '定西', '陇南', '临夏', '合作', '甘南', '西宁', '海东', '海北', '黄南', '海南州', '玉树', '海西', '银川', '石嘴山', '吴忠', '固原', '中卫', '乌鲁木齐', '克拉玛依', '吐鲁番', '哈密', '昌吉', '博州', '巴州', '阿克苏', '克州', '喀什', '和田', '伊犁', '塔城', '阿勒泰', '日喀则'],
}


class AirQualityDataLoader:
    def __init__(self, csv_path, coords_path):
        self.csv_path = csv_path
        with open(coords_path, 'r', encoding='utf-8') as f:
            self.city_coords = json.load(f)

        self._load_data()
        self._precompute_all()

    def _load_data(self):
        print(f"[DataLoader] Loading {self.csv_path} ...")
        dtypes = {
            '地区': 'category', '质量等级': 'category', '季节': 'category',
            '年份': 'int16', '月份': 'int8', '等级编码': 'int8',
            'AQI指数': 'float32', '当天AQI排名': 'float32',
            'PM2.5': 'float32', 'PM10': 'float32', 'So2': 'float32',
            'No2': 'float32', 'Co': 'float32', 'O3': 'float32'
        }
        self.df = pd.read_csv(self.csv_path, encoding='utf-8-sig', dtype=dtypes,
                              parse_dates=['日期'], low_memory=False)
        self.df['日期'] = pd.to_datetime(self.df['日期'], errors='coerce')
        # Drop rows with invalid dates
        self.df = self.df.dropna(subset=['日期'])
        self.df['year'] = self.df['日期'].dt.year.astype('int16')

        self.cities = sorted(self.df['地区'].dropna().unique().tolist())
        self.years = sorted(self.df['年份'].dropna().unique().astype(int).tolist())

        # Map city to region
        self.city_region = {}
        for region, cities_list in REGION_MAP.items():
            for c in cities_list:
                self.city_region[c] = region
        # Fill unknown cities
        for c in self.cities:
            if c not in self.city_region:
                self.city_region[c] = '其他'

        print(f"[DataLoader] Loaded {len(self.df):,} rows, {len(self.cities)} cities, "
              f"years {self.years[0]}-{self.years[-1]}")

    def _precompute_all(self):
        print("[DataLoader] Pre-computing all aggregations ...")

        # ---- Year-level aggregations ----
        self._yearly = {}
        for yr in self.years:
            ydf = self.df[self.df['年份'] == yr]
            self._yearly[yr] = {
                'avg_aqi': float(ydf['AQI指数'].mean()),
                'median_aqi': float(ydf['AQI指数'].median()),
                'aqi_std': float(ydf['AQI指数'].std()),
                'total_days': len(ydf),
                'city_count': ydf['地区'].nunique(),
            }

        # ---- Monthly aggregations (year × month) ----
        monthly_groups = self.df.groupby(['年份', '月份'], observed=False)
        self._monthly = defaultdict(dict)
        for (yr, mo), grp in monthly_groups:
            self._monthly[int(yr)][int(mo)] = {
                'avg_aqi': float(grp['AQI指数'].mean()),
                'min_aqi': float(grp['AQI指数'].min()),
                'max_aqi': float(grp['AQI指数'].max()),
                'avg_pm25': float(grp['PM2.5'].mean()),
                'avg_pm10': float(grp['PM10'].mean()),
                'avg_so2': float(grp['So2'].mean()),
                'avg_no2': float(grp['No2'].mean()),
                'avg_co': float(grp['Co'].mean()),
                'avg_o3': float(grp['O3'].mean()),
            }

        # ---- Seasonal aggregations (national) ----
        self._seasonal = defaultdict(dict)
        seasonal_groups = self.df.groupby(['年份', '季节'], observed=False)
        for (yr, season), grp in seasonal_groups:
            self._seasonal[int(yr)][season] = {
                'avg_aqi': float(grp['AQI指数'].mean()),
                'avg_pm25': float(grp['PM2.5'].mean()),
                'avg_pm10': float(grp['PM10'].mean()),
                'avg_so2': float(grp['So2'].mean()),
                'avg_no2': float(grp['No2'].mean()),
                'avg_co': float(grp['Co'].mean()),
                'avg_o3': float(grp['O3'].mean()),
            }

        # ---- City-specific seasonal aggregations ----
        self._city_seasonal = defaultdict(lambda: defaultdict(dict))
        city_seasonal_groups = self.df.groupby(['年份', '季节', '地区'], observed=False)
        for (yr, season, city), grp in city_seasonal_groups:
            self._city_seasonal[int(yr)][city][season] = {
                'avg_aqi': float(grp['AQI指数'].mean()),
                'avg_pm25': float(grp['PM2.5'].mean()),
                'avg_pm10': float(grp['PM10'].mean()),
                'avg_so2': float(grp['So2'].mean()),
                'avg_no2': float(grp['No2'].mean()),
                'avg_co': float(grp['Co'].mean()),
                'avg_o3': float(grp['O3'].mean()),
            }

        # ---- Fill missing seasons for partial years (2013, 2023) via multi-year averages ----
        complete_yrs = [y for y in self.years if y not in (2013, 2023)]
        if complete_yrs:
            # Compute monthly AQI averages from complete years
            ref_monthly = {}
            for mo in range(1, 13):
                ref = self.df[self.df['年份'].isin(complete_yrs) & (self.df['月份'] == mo)]
                if len(ref) > 0:
                    ref_monthly[mo] = {
                        'avg_aqi': float(ref['AQI指数'].mean()),
                        'avg_pm25': float(ref['PM2.5'].mean()),
                        'avg_pm10': float(ref['PM10'].mean()),
                        'avg_so2': float(ref['So2'].mean()),
                        'avg_no2': float(ref['No2'].mean()),
                        'avg_co': float(ref['Co'].mean()),
                        'avg_o3': float(ref['O3'].mean()),
                    }
            SEASON_MOONS = {'春': [3, 4, 5], '夏': [6, 7, 8], '秋': [9, 10, 11], '冬': [12, 1, 2]}
            fill_plan = {2013: ['春', '夏'], 2023: ['夏', '秋']}
            fields = ['avg_aqi', 'avg_pm25', 'avg_pm10', 'avg_so2', 'avg_no2', 'avg_co', 'avg_o3']
            for yr, fill_seasons in fill_plan.items():
                if yr not in self.years:
                    continue
                for season in fill_seasons:
                    if season in self._seasonal.get(yr, {}):
                        continue  # Already present
                    months = SEASON_MOONS[season]
                    vals = {f: 0.0 for f in fields}
                    cnt = 0
                    for mo in months:
                        if mo in ref_monthly:
                            for f in fields:
                                vals[f] += ref_monthly[mo][f]
                            cnt += 1
                    if cnt > 0:
                        for f in fields:
                            vals[f] = round(vals[f] / cnt, 2)
                        self._seasonal[yr][season] = vals
                        # Also add to city_seasonal for every city
                        yr_cities = self._city_seasonal.get(yr, {})
                        for city in yr_cities:
                            self._city_seasonal[yr][city][season] = vals

        # ---- City × Year aggregations ----
        city_year_groups = self.df.groupby(['地区', '年份'], observed=False)
        self._city_yearly = defaultdict(lambda: defaultdict(dict))
        for (city, yr), grp in city_year_groups:
            stats = {
                'avg_aqi': float(grp['AQI指数'].mean()),
                'avg_pm25': float(grp['PM2.5'].mean()),
                'avg_pm10': float(grp['PM10'].mean()),
                'avg_so2': float(grp['So2'].mean()),
                'avg_no2': float(grp['No2'].mean()),
                'avg_co': float(grp['Co'].mean()),
                'avg_o3': float(grp['O3'].mean()),
                'days': len(grp),
            }
            # Quality distribution per city per year
            qdist = grp['质量等级'].value_counts().to_dict()
            stats['quality_dist'] = {k: int(v) for k, v in qdist.items()}
            self._city_yearly[int(yr)][city] = stats

        # ---- YoY change ----
        self._yoy = {}
        for i, yr in enumerate(self.years):
            curr = self._yearly[yr]['avg_aqi']
            if i > 0:
                prev = self._yearly[self.years[i - 1]]['avg_aqi']
                pct = ((curr - prev) / prev) * 100 if prev else 0
            else:
                pct = 0
            self._yoy[int(yr)] = {
                'avg_aqi': curr,
                'delta': curr - prev if i > 0 else 0,
                'pct_change': round(pct, 2)
            }

        # ---- City ranking per year ----
        self._city_ranking = {}
        for yr in self.years:
            cities_data = []
            for city in self.cities:
                if city in self._city_yearly[int(yr)]:
                    d = self._city_yearly[int(yr)][city]
                    d['city'] = city
                    d['lat'] = self.city_coords.get(city, [116.4, 39.9])[1]
                    d['lng'] = self.city_coords.get(city, [116.4, 39.9])[0]
                    cities_data.append(d)
            cities_data.sort(key=lambda x: x['avg_aqi'], reverse=True)
            for idx, c in enumerate(cities_data):
                c['rank'] = idx + 1
            self._city_ranking[int(yr)] = cities_data

        # ---- Regional distribution ----
        self._regional = defaultdict(dict)
        for yr in self.years:
            region_data = defaultdict(list)
            for city in self.cities:
                if city in self._city_yearly[int(yr)]:
                    region = self.city_region.get(city, '其他')
                    region_data[region].append(self._city_yearly[int(yr)][city]['avg_aqi'])
            for region, aqis in region_data.items():
                self._regional[int(yr)][region] = {
                    'avg_aqi': round(sum(aqis) / len(aqis), 2),
                    'city_count': len(aqis),
                    'min_aqi': round(min(aqis), 2),
                    'max_aqi': round(max(aqis), 2),
                }

        # ---- Moving averages (national daily) ----
        self._moving_avg = {}
        daily_national = self.df.groupby('日期')['AQI指数'].mean().sort_index()
        self._moving_avg['daily'] = daily_national
        # Resample to ensure daily continuity and compute MA
        daily_full = daily_national.resample('D').mean().interpolate()
        self._moving_avg['ma7'] = daily_full.rolling(7, min_periods=1).mean()
        self._moving_avg['ma30'] = daily_full.rolling(30, min_periods=1).mean()

        # ---- Correlation matrix per year (7 vars: 6 pollutants + AQI) ----
        self._correlations = {}
        for yr in self.years:
            ydf = self.df[self.df['年份'] == yr][CORRELATION_VARS].dropna()
            if len(ydf) > 10:
                corr = ydf.corr().values.tolist()
            else:
                corr = [[0.0] * len(CORRELATION_VARS) for _ in range(len(CORRELATION_VARS))]
            self._correlations[int(yr)] = {
                'labels': CORRELATION_VARS,
                'matrix': [[round(float(v), 3) for v in row] for row in corr]
            }

        # ---- City clustering per year (KMeans on pollutant profile) ----
        self._clusters = {}
        for yr in self.years:
            features = []
            city_list = []
            for city in self.cities:
                if city in self._city_yearly[int(yr)]:
                    d = self._city_yearly[int(yr)][city]
                    features.append([d['avg_pm25'], d['avg_pm10'], d['avg_so2'],
                                     d['avg_no2'], d['avg_o3']])
                    city_list.append(city)
            if len(features) >= 5:
                scaled = StandardScaler().fit_transform(features)
                kmeans = KMeans(n_clusters=5, random_state=42, n_init=10)
                labels = kmeans.fit_predict(scaled)
                cluster_data = defaultdict(list)
                for c, lbl in zip(city_list, labels):
                    cluster_data[int(lbl)].append(c)
                # Compute cluster centers in original scale
                cluster_centers = {}
                for lbl, cities_in_cluster in cluster_data.items():
                    aqis = [self._city_yearly[int(yr)][c]['avg_aqi'] for c in cities_in_cluster]
                    cluster_centers[lbl] = {
                        'cities': cities_in_cluster,
                        'count': len(cities_in_cluster),
                        'avg_aqi': round(sum(aqis) / len(aqis), 2)
                    }
                self._clusters[int(yr)] = cluster_centers
            else:
                self._clusters[int(yr)] = {}

        # ---- Quality distribution per year ----
        self._quality_dist = {}
        for yr in self.years:
            ydf = self.df[self.df['年份'] == yr]
            qc = ydf['质量等级'].value_counts()
            total = int(qc.sum())
            self._quality_dist[int(yr)] = {
                level: {'count': int(qc.get(level, 0)),
                        'pct': round(float(qc.get(level, 0)) / total * 100, 2)}
                for level in QUALITY_LEVELS
            }

        # ---- Excellent/good day ratio per city per year ----
        self._good_ratio = defaultdict(dict)
        for yr in self.years:
            ydf = self.df[self.df['年份'] == yr]
            for city in self.cities:
                cdf = ydf[ydf['地区'] == city]
                if len(cdf) > 0:
                    good_days = len(cdf[cdf['质量等级'].isin(['优', '良'])])
                    self._good_ratio[int(yr)][city] = round(good_days / len(cdf) * 100, 2)

        # ---- Heavy pollution frequency ----
        self._heavy_pollution = defaultdict(dict)
        for yr in self.years:
            ydf = self.df[self.df['年份'] == yr]
            for city in self.cities:
                cdf = ydf[ydf['地区'] == city]
                if len(cdf) > 0:
                    heavy = len(cdf[cdf['质量等级'].isin(['重度污染', '严重污染'])])
                    self._heavy_pollution[int(yr)][city] = {
                        'count': int(heavy),
                        'pct': round(heavy / len(cdf) * 100, 2)
                    }

        # ---- Primary pollutant per city per year ----
        self._primary_pollutant = defaultdict(dict)
        for yr in self.years:
            for city in self.cities:
                if city in self._city_yearly[int(yr)]:
                    d = self._city_yearly[int(yr)][city]
                    vals = {p: d[f'avg_{p.lower().replace(".", "").replace("2.5", "25").replace("o3", "o3")}'] if f'avg_{p.lower().replace(".", "").replace("2.5", "25")}' in d else 0 for p in POLLUTANTS}
                    # Actually use the correct keys
                    vals2 = {
                        'PM2.5': d.get('avg_pm25', 0),
                        'PM10': d.get('avg_pm10', 0),
                        'So2': d.get('avg_so2', 0),
                        'No2': d.get('avg_no2', 0),
                        'Co': d.get('avg_co', 0),
                        'O3': d.get('avg_o3', 0),
                    }
                    if vals2:
                        primary = max(vals2, key=vals2.get)
                        self._primary_pollutant[int(yr)][city] = primary

        # ---- PM2.5/PM10 ratio per city per year ----
        self._pm_ratio = defaultdict(dict)
        for yr in self.years:
            for city in self.cities:
                if city in self._city_yearly[int(yr)]:
                    d = self._city_yearly[int(yr)][city]
                    pm25 = d.get('avg_pm25', 0)
                    pm10 = d.get('avg_pm10', 1)
                    self._pm_ratio[int(yr)][city] = round(pm25 / pm10, 3) if pm10 > 0 else 0

        # ---- Pollution episodes (consecutive heavy pollution) ----
        self._episodes = defaultdict(list)
        for yr in self.years:
            ydf = self.df[self.df['年份'] == yr].sort_values(['地区', '日期'])
            for city in self.cities:
                cdf = ydf[ydf['地区'] == city].sort_values('日期')
                if len(cdf) < 3:
                    continue
                is_polluted = (cdf['AQI指数'] > 150).astype(int)
                if is_polluted.sum() == 0:
                    continue
                # Find consecutive runs
                runs = (is_polluted != is_polluted.shift()).cumsum()
                polluted_runs = is_polluted.groupby(runs)
                for run_id, mask in polluted_runs:
                    if mask.iloc[0] == 0:
                        continue
                    run_data = cdf.loc[mask.index]
                    if len(run_data) >= 3:
                        self._episodes[int(yr)].append({
                            'city': city,
                            'start_date': run_data['日期'].iloc[0].strftime('%Y-%m-%d'),
                            'end_date': run_data['日期'].iloc[-1].strftime('%Y-%m-%d'),
                            'duration': int(len(run_data)),
                            'max_aqi': float(run_data['AQI指数'].max()),
                            'avg_aqi': round(float(run_data['AQI指数'].mean()), 1),
                        })

        # ---- City × Month Heatmap ----
        self._heatmap = {}
        for yr in self.years:
            pivot = self.df[self.df['年份'] == yr].pivot_table(
                values='AQI指数', index='地区', columns='月份', aggfunc='mean', observed=False
            )
            # Sort cities by annual avg AQI
            city_order = pivot.mean(axis=1).sort_values(ascending=True).index.tolist()
            self._heatmap[int(yr)] = {
                'cities': city_order,
                'months': MONTH_NAMES,
                'data': [[round(float(pivot.loc[c, mo]), 1) if (c in pivot.index and mo in pivot.columns and not pd.isna(pivot.loc[c, mo])) else None
                          for mo in range(1, 13)] for c in city_order]
            }

        # ---- City similarity (top 100 cities by data completeness) ----
        self._similarity = {}
        for yr in self.years:
            features = []
            city_list = []
            for city in self.cities:
                if city in self._city_yearly[int(yr)]:
                    d = self._city_yearly[int(yr)][city]
                    features.append([d['avg_pm25'], d['avg_pm10'], d['avg_so2'],
                                     d['avg_no2'], d['avg_o3'], d['avg_co']])
                    city_list.append(city)
            if len(features) >= 10:
                scaled = StandardScaler().fit_transform(features)
                # Only compute for top 50 to keep it manageable
                top_n = min(50, len(features))
                dists = squareform(pdist(scaled[:top_n], 'euclidean'))
                similar_pairs = []
                for i in range(top_n):
                    for j in range(i + 1, top_n):
                        similar_pairs.append({
                            'city1': city_list[i],
                            'city2': city_list[j],
                            'distance': round(float(dists[i][j]), 3)
                        })
                # Sort and keep top 50 closest pairs
                similar_pairs.sort(key=lambda x: x['distance'])
                self._similarity[int(yr)] = similar_pairs[:50]
            else:
                self._similarity[int(yr)] = []

        # ---- Level transition matrix per year ----
        self._level_transitions = {}
        for yr in self.years:
            matrix = defaultdict(lambda: defaultdict(int))
            ydf = self.df[self.df['年份'] == yr].sort_values(['地区', '日期'])
            for city in self.cities:
                cdf = ydf[ydf['地区'] == city]
                if len(cdf) < 2:
                    continue
                levels = cdf['质量等级'].tolist()
                for l1, l2 in zip(levels[:-1], levels[1:]):
                    matrix[l1][l2] += 1
            # Convert to list of rows
            self._level_transitions[int(yr)] = {
                'labels': QUALITY_LEVELS,
                'matrix': [[int(matrix[l1].get(l2, 0)) for l2 in QUALITY_LEVELS] for l1 in QUALITY_LEVELS]
            }

        # ---- Provincial aggregation (simplified: use city_region as province) ----
        # Already covered by regional

        # ---- Pollutant annual composition ----
        self._pollutant_composition = {}
        for yr in self.years:
            comp = {}
            for pol in POLLUTANTS:
                col = pol
                vals = self.df[self.df['年份'] == yr][col].dropna()
                comp[pol] = {
                    'avg': round(float(vals.mean()), 2),
                    'max': round(float(vals.max()), 2),
                    'min': round(float(vals.min()), 2),
                    'std': round(float(vals.std()), 2),
                }
            self._pollutant_composition[int(yr)] = comp

        print("[DataLoader] All pre-computations complete.")

    def _get_pollutant_trends_national(self, yr):
        """Compute monthly pollutant trends for national level (used by both national and city endpoints)."""
        trends = {}
        for pol in POLLUTANTS:
            col = pol
            monthly_vals = self.df[self.df['年份'] == yr].groupby('月份')[col].mean()
            trends[pol] = [
                {'month': int(mo), 'month_name': MONTH_NAMES[int(mo) - 1], 'avg': round(float(v), 2)}
                for mo, v in monthly_vals.items()
            ]
        return trends

    def _get_pollutant_trends_city(self, yr, city):
        """Compute monthly pollutant trends for a specific city."""
        cdf = self.df[(self.df['年份'] == yr) & (self.df['地区'] == city)]
        if len(cdf) == 0:
            return {}
        trends = {}
        for pol in POLLUTANTS:
            monthly_vals = cdf.groupby('月份')[pol].mean()
            trends[pol] = [
                {'month': int(mo), 'month_name': MONTH_NAMES[int(mo) - 1], 'avg': round(float(v), 2)}
                for mo, v in monthly_vals.items()
            ]
        return trends

    def _get_level_transitions_city(self, yr, city):
        """Compute level transition matrix for a specific city."""
        from collections import defaultdict as dd
        cdf = self.df[(self.df['年份'] == yr) & (self.df['地区'] == city)].sort_values('日期')
        if len(cdf) < 2:
            return {'labels': QUALITY_LEVELS, 'matrix': [[0]*6 for _ in range(6)]}
        matrix = dd(lambda: dd(int))
        levels = cdf['质量等级'].tolist()
        for l1, l2 in zip(levels[:-1], levels[1:]):
            matrix[l1][l2] += 1
        return {
            'labels': QUALITY_LEVELS,
            'matrix': [[int(matrix[l1].get(l2, 0)) for l2 in QUALITY_LEVELS] for l1 in QUALITY_LEVELS]
        }

    # ========== Public API methods ==========

    def get_overview(self, year):
        yr = int(year)
        yoy_prev = self._yoy.get(yr - 1, {})
        yoy_curr = self._yoy.get(yr, {})
        quality = self._quality_dist.get(yr, {})
        seasonal_summary = {}
        for s in SEASONS:
            if s in self._seasonal.get(yr, {}):
                seasonal_summary[s] = {'avg_aqi': self._seasonal[yr][s]['avg_aqi']}

        rank = self._city_ranking.get(yr, [])
        best_city = rank[-1] if rank else {}
        worst_city = rank[0] if rank else {}

        return {
            'year': yr,
            'avg_aqi': round(self._yearly[yr]['avg_aqi'], 2),
            'median_aqi': round(self._yearly[yr]['median_aqi'], 2),
            'aqi_std': round(self._yearly[yr]['aqi_std'], 2),
            'best_city': best_city.get('city', ''),
            'best_city_aqi': round(best_city.get('avg_aqi', 0), 2),
            'worst_city': worst_city.get('city', ''),
            'worst_city_aqi': round(worst_city.get('avg_aqi', 0), 2),
            'total_cities': self._yearly[yr]['city_count'],
            'total_days': self._yearly[yr]['total_days'],
            'quality_distribution': quality,
            'year_over_year_change': yoy_curr.get('pct_change', 0),
            'seasonal_summary': seasonal_summary,
        }

    def get_temporal(self, year, city='all'):
        yr = int(year)
        result = {'year': yr, 'city': city}

        if city == 'all':
            # Monthly trend (national)
            monthly_trend = []
            for mo in range(1, 13):
                if mo in self._monthly.get(yr, {}):
                    d = self._monthly[yr][mo]
                    monthly_trend.append({
                        'month': mo, 'month_name': MONTH_NAMES[mo - 1],
                        'avg_aqi': round(d['avg_aqi'], 2),
                        'min_aqi': round(d.get('min_aqi', d['avg_aqi']), 2),
                        'max_aqi': round(d.get('max_aqi', d['avg_aqi']), 2),
                        'avg_pm25': round(d['avg_pm25'], 2),
                        'avg_pm10': round(d['avg_pm10'], 2),
                        'avg_so2': round(d['avg_so2'], 2),
                        'avg_no2': round(d['avg_no2'], 2),
                        'avg_co': round(d['avg_co'], 2),
                        'avg_o3': round(d['avg_o3'], 2),
                    })
            result['monthly_trend'] = monthly_trend

            # Seasonal
            seasonal = {}
            for s in SEASONS:
                if s in self._seasonal.get(yr, {}):
                    seasonal[s] = {k: round(v, 2) for k, v in self._seasonal[yr][s].items()}
            result['seasonal'] = seasonal

            # YoY comparison
            yoy = [{'year': int(y), 'avg_aqi': round(self._yearly[y]['avg_aqi'], 2),
                    'pct_change': self._yoy[y]['pct_change']}
                   for y in self.years]
            result['yoy_comparison'] = yoy

            # Moving averages
            daily = self._moving_avg['daily']
            ma7 = self._moving_avg['ma7']
            ma30 = self._moving_avg['ma30']
            result['moving_averages'] = [
                {
                    'date': str(d.date()),
                    'aqi': round(float(daily.get(d, float('nan'))), 2) if d in daily.index else None,
                    'ma7': round(float(ma7.get(d, float('nan'))), 2) if d in ma7.index else None,
                    'ma30': round(float(ma30.get(d, float('nan'))), 2) if d in ma30.index else None,
                }
                for d in daily.index[::7]  # Sample weekly to keep size manageable
            ]

            # Best/worst months
            if monthly_trend:
                best = min(monthly_trend, key=lambda x: x['avg_aqi'])
                worst = max(monthly_trend, key=lambda x: x['avg_aqi'])
                result['best_month'] = {'month': best['month'], 'month_name': best['month_name'], 'avg_aqi': best['avg_aqi']}
                result['worst_month'] = {'month': worst['month'], 'month_name': worst['month_name'], 'avg_aqi': worst['avg_aqi']}
        else:
            # City-specific temporal data
            if city in self._city_yearly.get(yr, {}):
                d = self._city_yearly[yr][city]
                result['avg_aqi'] = round(d['avg_aqi'], 2)
                result['avg_pm25'] = round(d['avg_pm25'], 2)
                result['avg_pm10'] = round(d['avg_pm10'], 2)
                result['avg_so2'] = round(d['avg_so2'], 2)
                result['avg_no2'] = round(d['avg_no2'], 2)
                result['avg_co'] = round(d['avg_co'], 2)
                result['avg_o3'] = round(d['avg_o3'], 2)
                result['quality_distribution'] = d.get('quality_dist', {})

                # City monthly trend
                city_monthly = []
                cdf = self.df[(self.df['年份'] == yr) & (self.df['地区'] == city)]
                for mo in range(1, 13):
                    mdf = cdf[cdf['月份'] == mo]
                    if len(mdf) > 0:
                        city_monthly.append({
                            'month': mo, 'month_name': MONTH_NAMES[mo - 1],
                            'avg_aqi': round(float(mdf['AQI指数'].mean()), 2),
                            'min_aqi': round(float(mdf['AQI指数'].min()), 2),
                            'max_aqi': round(float(mdf['AQI指数'].max()), 2),
                            'avg_pm25': round(float(mdf['PM2.5'].mean()), 2),
                            'avg_pm10': round(float(mdf['PM10'].mean()), 2),
                        })
                result['monthly_trend'] = city_monthly

                # City rank
                rank = self._city_ranking.get(yr, [])
                city_rank = next((r['rank'] for r in rank if r['city'] == city), None)
                result['rank'] = city_rank
                result['total_cities'] = len(rank)

                # Primary pollutant
                result['primary_pollutant'] = self._primary_pollutant.get(yr, {}).get(city, '')

                # City-specific YoY comparison
                result['yoy_comparison'] = []
                for y in self.years:
                    if city in self._city_yearly.get(y, {}):
                        cur_aqi = self._city_yearly[y][city]['avg_aqi']
                        prev_aqi = self._city_yearly.get(y-1, {}).get(city, {}).get('avg_aqi', cur_aqi)
                        pct = round((cur_aqi - prev_aqi) / prev_aqi * 100, 2) if prev_aqi else 0
                        result['yoy_comparison'].append({
                            'year': int(y), 'avg_aqi': round(cur_aqi, 2), 'pct_change': pct
                        })
                # City-specific seasonal data (fallback to national if city not available)
                city_seasonal = self._city_seasonal.get(yr, {}).get(city, {})
                if city_seasonal:
                    result['seasonal'] = {s: {k: round(v, 2) for k, v in vals.items()}
                                          for s, vals in city_seasonal.items()}
                else:
                    seasonal_nat = {}
                    for s in SEASONS:
                        if s in self._seasonal.get(yr, {}):
                            seasonal_nat[s] = {k: round(v, 2) for k, v in self._seasonal[yr][s].items()}
                    result['seasonal'] = seasonal_nat
                # Best/worst from national monthly
                nat_monthly = []
                for mo in range(1, 13):
                    if mo in self._monthly.get(yr, {}):
                        d2 = self._monthly[yr][mo]
                        nat_monthly.append({'month': mo, 'month_name': MONTH_NAMES[mo - 1], 'avg_aqi': round(d2['avg_aqi'], 2)})
                if nat_monthly:
                    best_nat = min(nat_monthly, key=lambda x: x['avg_aqi'])
                    worst_nat = max(nat_monthly, key=lambda x: x['avg_aqi'])
                    result['best_month'] = {'month': best_nat['month'], 'month_name': best_nat['month_name'], 'avg_aqi': best_nat['avg_aqi']}
                    result['worst_month'] = {'month': worst_nat['month'], 'month_name': worst_nat['month_name'], 'avg_aqi': worst_nat['avg_aqi']}

            else:
                result['error'] = f'City {city} not found in year {yr}'

        return result

    def get_spatial(self, year):
        yr = int(year)
        rank = self._city_ranking.get(yr, [])

        # Top 50 for ranking display
        city_ranking = []
        for r in rank:
            city_ranking.append({
                'rank': r['rank'],
                'city': r['city'],
                'avg_aqi': round(r['avg_aqi'], 2),
                'avg_pm25': round(r['avg_pm25'], 2),
                'avg_pm10': round(r['avg_pm10'], 2),
                'lat': r['lat'],
                'lng': r['lng'],
                'good_ratio': self._good_ratio.get(yr, {}).get(r['city'], 0),
                'heavy_pollution_pct': self._heavy_pollution.get(yr, {}).get(r['city'], {}).get('pct', 0),
            })

        # Regional distribution
        regional = self._regional.get(yr, {})

        # Clusters
        clusters = {}
        for lbl, data in self._clusters.get(yr, {}).items():
            clusters[str(lbl)] = data

        # Hotspots: cities with AQI > national average + 1 std
        national_avg = self._yearly[yr]['avg_aqi']
        national_std = self._yearly[yr]['aqi_std']
        threshold = national_avg + national_std
        hotspots = [{
            'city': r['city'],
            'avg_aqi': round(r['avg_aqi'], 2),
            'lat': r['lat'],
            'lng': r['lng'],
            'intensity': round((r['avg_aqi'] - national_avg) / national_std, 2) if national_std > 0 else 0,
        } for r in rank if r['avg_aqi'] > threshold]

        return {
            'year': yr,
            'city_ranking': city_ranking,
            'top10': [r for r in city_ranking if r['rank'] <= 50],
            'bottom10': [r for r in city_ranking if r['rank'] > len(city_ranking) - 10],
            'regional_distribution': regional,
            'city_clusters': clusters,
            'hotspots': hotspots,
        }

    def get_pollutants(self, year, city='all'):
        yr = int(year)
        result = {'year': yr, 'city': city}

        if city == 'all':
            # Pollutant trends (monthly for each pollutant)
            result['pollutant_trends'] = self._get_pollutant_trends_national(yr)

            # Correlation matrix
            result['correlation_matrix'] = self._correlations.get(yr, {})

            # Primary pollutant distribution
            primary_counts = defaultdict(int)
            for city, pol in self._primary_pollutant.get(yr, {}).items():
                primary_counts[pol] += 1
            total = sum(primary_counts.values())
            result['primary_pollutant_distribution'] = [
                {'pollutant': pol, 'count': primary_counts.get(pol, 0),
                 'pct': round(primary_counts.get(pol, 0) / total * 100, 2) if total > 0 else 0}
                for pol in POLLUTANTS
            ]

            # PM ratio stats
            pm_ratios = [v for v in self._pm_ratio.get(yr, {}).values() if v > 0]
            if pm_ratios:
                result['pm_ratio_stats'] = {
                    'avg': round(sum(pm_ratios) / len(pm_ratios), 3),
                    'max': round(max(pm_ratios), 3),
                    'min': round(min(pm_ratios), 3),
                    'cities_high': sorted([
                        {'city': c, 'ratio': r}
                        for c, r in self._pm_ratio.get(yr, {}).items() if r > 0
                    ], key=lambda x: x['ratio'], reverse=True)[:10],
                    'cities_low': sorted([
                        {'city': c, 'ratio': r}
                        for c, r in self._pm_ratio.get(yr, {}).items() if r > 0
                    ], key=lambda x: x['ratio'])[:10],
                }

            # Pollutant composition
            result['pollutant_composition'] = self._pollutant_composition.get(yr, {})
        else:
            # City-specific pollutant data
            if city in self._city_yearly.get(yr, {}):
                d = self._city_yearly[yr][city]
                result['pollutant_values'] = {
                    'PM2.5': round(d['avg_pm25'], 2),
                    'PM10': round(d['avg_pm10'], 2),
                    'So2': round(d['avg_so2'], 2),
                    'No2': round(d['avg_no2'], 2),
                    'Co': round(d['avg_co'], 2),
                    'O3': round(d['avg_o3'], 2),
                }
                result['primary_pollutant'] = self._primary_pollutant.get(yr, {}).get(city, '')
                result['pm_ratio'] = self._pm_ratio.get(yr, {}).get(city, 0)
                # City-specific pollutant trends (compute on-the-fly)
                result['pollutant_trends'] = self._get_pollutant_trends_city(yr, city)
                # City-specific correlation matrix (7 vars: 6 pollutants + AQI)
                cdf = self.df[(self.df['年份'] == yr) & (self.df['地区'] == city)][CORRELATION_VARS].dropna()
                if len(cdf) > 10:
                    corr = cdf.corr()
                    corr = corr.where(corr.notna(), None).values.tolist()
                    result['correlation_matrix'] = {
                        'labels': CORRELATION_VARS,
                        'matrix': [[round(float(v), 3) if v is not None else None for v in row] for row in corr]
                    }
                else:
                    result['correlation_matrix'] = self._correlations.get(yr, {})
                result['pollutant_composition'] = self._pollutant_composition.get(yr, {})
                # Primary pollutant distribution
                primary_counts = defaultdict(int)
                for c2, pol in self._primary_pollutant.get(yr, {}).items():
                    primary_counts[pol] += 1
                total_pc = sum(primary_counts.values())
                result['primary_pollutant_distribution'] = [
                    {'pollutant': pol, 'count': primary_counts.get(pol, 0),
                     'pct': round(primary_counts.get(pol, 0) / total_pc * 100, 2) if total_pc > 0 else 0}
                    for pol in POLLUTANTS
                ]
                # PM ratio stats
                pm_ratios = [v for v in self._pm_ratio.get(yr, {}).values() if v > 0]
                if pm_ratios:
                    result['pm_ratio_stats'] = {
                        'avg': round(sum(pm_ratios) / len(pm_ratios), 3),
                        'max': round(max(pm_ratios), 3),
                        'min': round(min(pm_ratios), 3),
                    }

        return result

    def get_quality(self, year, city='all'):
        yr = int(year)
        result = {'year': yr, 'city': city}

        quality = self._quality_dist.get(yr, {})
        result['level_distribution'] = quality

        # Good ratio (all cities)
        good_ratios = self._good_ratio.get(yr, {})
        result['excellent_good_ratio'] = sorted([
            {'city': c, 'ratio': r} for c, r in good_ratios.items()
        ], key=lambda x: x['ratio'], reverse=True)

        # Heavy pollution frequency
        heavy = self._heavy_pollution.get(yr, {})
        result['heavy_pollution_frequency'] = sorted([
            {'city': c, 'count': h['count'], 'pct': h['pct']}
            for c, h in heavy.items()
        ], key=lambda x: x['pct'], reverse=True)

        # Level transitions
        result['level_transition_matrix'] = self._level_transitions.get(yr, {})

        # Always include national level transition matrix and distribution
        result['level_transition_matrix'] = self._level_transitions.get(yr, {})
        result['level_distribution'] = quality

        if city != 'all':
            cdata = self._city_yearly.get(yr, {}).get(city, {})
            result['city_quality'] = cdata.get('quality_dist', {})
            # City-specific level transition matrix
            result['level_transition_matrix'] = self._get_level_transitions_city(yr, city)
            # City-specific level distribution
            cq = cdata.get('quality_dist', {})
            total_cq = sum(cq.values())
            if total_cq > 0:
                result['level_distribution'] = {
                    level: {'count': cq.get(level, 0),
                            'pct': round(cq.get(level, 0) / total_cq * 100, 2)}
                    for level in QUALITY_LEVELS
                }
                result['total_days'] = total_cq

        return result

    def get_advanced(self, year):
        yr = int(year)
        result = {'year': yr}

        # Seasonal decomposition (simplified using monthly data)
        monthly = self._monthly.get(yr, {})
        if monthly:
            trend_values = [monthly.get(mo, {}).get('avg_aqi', 0) for mo in range(1, 13)]
            overall_mean = sum(trend_values) / len(trend_values) if trend_values else 0
            seasonal_values = [v - overall_mean for v in trend_values]
            result['seasonal_decomposition'] = {
                'trend': [round(v, 2) for v in trend_values],
                'seasonal': [round(v, 2) for v in seasonal_values],
                'residual': [0.0] * 12,
                'months': MONTH_NAMES,
            }

        # City x Month heatmap
        result['city_month_heatmap'] = self._heatmap.get(yr, {})

        # Pollution episodes
        result['pollution_episodes'] = self._episodes.get(yr, [])

        # City similarity
        result['city_similarity'] = self._similarity.get(yr, [])

        return result

    def get_city_detail(self, city, year):
        yr = int(year)

        if city not in self._city_yearly.get(yr, {}):
            return {'error': f'City {city} not found in year {yr}'}

        d = self._city_yearly[yr][city]
        rank = self._city_ranking.get(yr, [])
        city_rank = next((r['rank'] for r in rank if r['city'] == city), None)

        # Compute year-over-year change for this city
        yoy_change = None
        if city in self._city_yearly.get(yr - 1, {}):
            prev_aqi = self._city_yearly[yr - 1][city]['avg_aqi']
            curr_aqi = d['avg_aqi']
            yoy_change = round((curr_aqi - prev_aqi) / prev_aqi * 100, 2) if prev_aqi else 0

        # Monthly data
        monthly = []
        cdf = self.df[(self.df['年份'] == yr) & (self.df['地区'] == city)]
        for mo in range(1, 13):
            mdf = cdf[cdf['月份'] == mo]
            if len(mdf) > 0:
                monthly.append({
                    'month': mo, 'month_name': MONTH_NAMES[mo - 1],
                    'avg_aqi': round(float(mdf['AQI指数'].mean()), 2),
                    'avg_pm25': round(float(mdf['PM2.5'].mean()), 2),
                    'avg_pm10': round(float(mdf['PM10'].mean()), 2),
                    'day_count': len(mdf),
                })

        # Rank history
        rank_history = []
        for y in self.years:
            if city in self._city_yearly.get(y, {}):
                rank_history.append({
                    'year': int(y),
                    'avg_aqi': round(self._city_yearly[y][city]['avg_aqi'], 2),
                })

        return {
            'city': city,
            'year': yr,
            'avg_aqi': round(d['avg_aqi'], 2),
            'avg_pm25': round(d['avg_pm25'], 2),
            'avg_pm10': round(d['avg_pm10'], 2),
            'avg_so2': round(d['avg_so2'], 2),
            'avg_no2': round(d['avg_no2'], 2),
            'avg_co': round(d['avg_co'], 2),
            'avg_o3': round(d['avg_o3'], 2),
            'quality_distribution': d.get('quality_dist', {}),
            'monthly_trend': monthly,
            'rank': city_rank,
            'total_cities': len(rank),
            'yoy_change': yoy_change,
            'primary_pollutant': self._primary_pollutant.get(yr, {}).get(city, ''),
            'pm_ratio': self._pm_ratio.get(yr, {}).get(city, 0),
            'good_ratio': self._good_ratio.get(yr, {}).get(city, 0),
            'heavy_pollution': self._heavy_pollution.get(yr, {}).get(city, {}),
            'rank_history': rank_history,
            'lat': self.city_coords.get(city, [116.4, 39.9])[0],
            'lng': self.city_coords.get(city, [116.4, 39.9])[1],
        }

    def get_cities(self):
        # Compute available years per city
        city_years = {}
        for yr in self.years:
            for city in self._city_yearly.get(int(yr), {}):
                if city not in city_years:
                    city_years[city] = []
                city_years[city].append(int(yr))
        return [{
            'city': c,
            'lng': self.city_coords.get(c, [116.4, 39.9])[0],
            'lat': self.city_coords.get(c, [116.4, 39.9])[1],
            'years': sorted(city_years.get(c, [])),
        } for c in self.cities]

    def get_years(self):
        return [int(y) for y in self.years]
