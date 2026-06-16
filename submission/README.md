# 空气质量智能分析平台 — 数据提交材料

## 目录结构

```
submission/
├── README.docx                # 本文件（材料清单）
├── 数据来源说明.docx            # 数据来源详细说明（含网址和截图）
├── 数据探查记录表.docx          # 数据探查记录（字段分析、质量评估）
├── 原始数据集.csv              # 合并后的原始数据集（29.0 MB，588,716 行）
├── data_summary.txt           # 数据集统计摘要
├── screenshots/               # 网站截图
│   ├── 01_homepage.png
│   ├── 02_city_monthly.png
│   └── 03_daily_data.png
└── data_sample/               # 数据样本
    ├── sample_1000.csv        # 随机 1000 条样本
    └── representative_by_year.csv  # 各年代表数据
```

## 数据集概览

| 项目 | 内容 |
|------|------|
| 原始数据集 | `原始数据集.csv` (29.0 MB, 588,716 行) |
| 数据源文件 | 197 个城市 CSV（188 个含有效数据） |
| 覆盖城市 | 188 个中国城市 |
| 时间跨度 | 2013 年 10 月 ~ 2023 年 5 月 |
| 数据字段 | 11 列（地区、日期、质量等级、AQI指数、当天AQI排名、PM2.5、PM10、SO2、NO2、CO、O3） |
| 数据来源 | 中国空气质量在线监测分析平台 (aqistudy.cn) |
| 采集方式 | Python 爬虫 + Playwright 浏览器自动化 |
| 文件编码 | UTF-8 with BOM（原始文件含 3 个 GBK 编码，已统一转换） |
| 缺失文件 | 9 个城市文件为空（guoluo/huaian/lianyunguang/shangluo/suqian/yancheng/yangzhou/yilihasakezhou/zhenjiang） |

## 原始数据说明

本数据集为从 aqistudy.cn 直接爬取的原始数据，未经任何清洗处理。

数据特点：
- 每个城市独立 CSV 文件，以城市拼音命名
- 原始文件存放路径：`D:\Desktop\作业\数据可视化\爬虫数据（部分原始数据)\`
- 合并文件已统一编码为 UTF-8 with BOM
- 数据包含少量质量问题（表头误入、离群值、同名城市），详见数据探查记录表

## 数据字段

| 字段 | 说明 |
|------|------|
| 地区 | 城市拼音（如 beijing, shanghai） |
| 日期 | YYYY-MM-DD 或 YYYY/MM/DD |
| 质量等级 | 优/良/轻度污染/中度污染/重度污染/严重污染 |
| AQI指数 | 0-500 |
| 当天AQI排名 | 全国城市排名 |
| PM2.5 | μg/m³ |
| PM10 | μg/m³ |
| So2 | μg/m³ |
| No2 | μg/m³ |
| Co | mg/m³ |
| O3 | μg/m³ |
