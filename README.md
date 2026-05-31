# Air Quality Smart Dashboard

中国城市空气质量可视化分析仪表盘，覆盖 **2013-2023** 年 **182 个城市** 的空气质量数据。

## 功能

- KPI 概览：年均 AQI、最佳/最差城市、质量分布
- 时间维度分析：月趋势、季节变化、同比、移动平均
- 空间维度分析：城市排名、区域分布、污染热力图
- 污染物分析：PM2.5/PM10/SO2/NO2/CO/O3 趋势、相关性矩阵
- 质量等级分析：等级分布、优良率、重污染频率、等级转移矩阵
- 高级分析：季节分解、城市×月份热力图、污染事件、城市相似性

## 技术栈

- **后端**：Python / Flask
- **前端**：ECharts + 原生 HTML/CSS/JS
- **数据处理**：Pandas / NumPy / scikit-learn

## 快速开始

```bash
# 安装依赖
pip install -r backend/requirements.txt

# 启动服务
cd backend
python app.py

# 浏览器访问
# http://localhost:5000
```

## API 端点

| 端点 | 说明 |
|------|------|
| `/api/overview` | KPI 概览 |
| `/api/temporal` | 时间分析 |
| `/api/spatial` | 空间分析 |
| `/api/pollutants` | 污染物分析 |
| `/api/quality` | 质量等级分析 |
| `/api/advanced` | 高级分析 |
| `/api/city/<name>` | 城市详情 |
| `/api/cities` | 城市列表 |
| `/api/years` | 年份列表 |

## 数据来源

数据来源于中国空气质量历史监测数据。

## License

MIT
