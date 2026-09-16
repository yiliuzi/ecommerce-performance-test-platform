# Ecommerce Performance Test Platform

基于 Locust、Prometheus 和 Grafana 搭建的电商接口性能测试平台，对商品查询、健康检查和订单创建等接口执行基准、阶梯、混合、峰值及稳定性测试，并通过监控数据定位数据库连接池瓶颈。

## 技术栈

- Python 3.13
- Locust 2.46
- FastAPI
- MySQL
- SQLAlchemy
- Prometheus
- Grafana

## 项目结构

```text
ecommerce-performance-test-platform/
├── locustfiles/
│   ├── basic_load_test.py
│   ├── step_load_test.py
│   ├── peak_load_test.py
│   ├── stability_test.py
│   └── order_mixed_test.py
├── monitoring/
│   ├── grafana/
│   │   └── ecommerce-api-dashboard.json
│   └── prometheus/
│       └── prometheus.yml
├── scripts/
│   └── cleanup_test_orders.py
├── reports/
├── .env.example
├── .gitignore
├── requirements.txt
└── README.md
```

## 测试场景

| 场景 | 测试目标 |
|---|---|
| 基准测试 | 验证低并发下接口基础性能 |
| 阶梯负载测试 | 逐步增加用户数并识别性能拐点 |
| 混合业务测试 | 模拟商品查询、订单查询和订单创建 |
| 峰值测试 | 验证高并发下系统吞吐量与失败率 |
| 稳定性测试 | 验证持续负载下的响应时间和可用性 |

## 测试结果

| 场景 | 并发用户 | 请求数 | 平均响应时间 | P95 | P99 | RPS | 失败率 |
|---|---:|---:|---:|---:|---:|---:|---:|
| 基准测试 | 10 | 314 | 5.37 ms | 6 ms | 9 ms | 4.9 | 0% |
| 阶梯负载 | 100 | 11,204 | 29 ms | 190 ms | 250 ms | 92.9 | 0% |
| 混合业务 | 20 | 1,162 | 5.49 ms | 10 ms | 37 ms | 19.5 | 0% |
| 峰值优化前 | 300 | 7,514 | 597.82 ms | 2,100 ms | 30,000 ms | 61.03 | 1.06% |
| 峰值优化后 | 300 | 19,690 | 589.7 ms | 5,500 ms | 15,000 ms | 132 | 2.03% |
| 稳定性测试 | 100 | 29,800 | 460.5 ms | 560 ms | 590 ms | 99.48 | 0% |

## 性能分析

峰值测试期间出现 SQLAlchemy 数据库连接池耗尽：

```text
QueuePool limit reached, connection timed out
```

通过调整连接池参数进行优化：

- `pool_size=20`
- `max_overflow=20`
- `pool_timeout=5`
- `pool_recycle=1800`
- `pool_pre_ping=True`
- `pool_use_lifo=True`

优化后：

- 吞吐量由 `61.03 RPS` 提升至 `132 RPS`
- 总请求数由 `7,514` 提升至 `19,690`
- P99 由 `30 s` 降低至 `15 s`
- 最大响应时间由约 `60 s` 降低至约 `20.55 s`

系统在 100 用户下能够保持稳定运行；300 用户峰值场景仍超过当前单机服务和数据库连接池的处理能力，容量边界位于 100 至 200 并发用户之间。

## 监控指标

Grafana Dashboard 包含：

- 实时请求速率
- HTTP 5xx 失败率
- P95 响应时间
- 各接口请求速率
- 平均响应时间
- API 进程内存占用

FastAPI 指标地址：

```text
http://127.0.0.1:8000/metrics
```

Prometheus：

```text
http://127.0.0.1:9090
```

Grafana：

```text
http://127.0.0.1:3000
```

## 安装依赖

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

## 运行基准测试

```powershell
python -m locust `
  -f locustfiles\basic_load_test.py `
  --host http://127.0.0.1:8000 `
  --headless `
  -u 10 `
  -r 2 `
  -t 1m
```

## 运行阶梯负载测试

```powershell
python -m locust `
  -f locustfiles\step_load_test.py `
  --host http://127.0.0.1:8000
```

然后访问：

```text
http://127.0.0.1:8089
```

## 运行稳定性测试

```powershell
python -m locust `
  -f locustfiles\stability_test.py `
  --host http://127.0.0.1:8000 `
  --headless `
  -u 100 `
  -r 10 `
  -t 5m
```

## 测试数据清理

混合场景只记录并删除压测期间创建的订单，避免误删原始业务数据：

```powershell
python scripts\cleanup_test_orders.py
```

待删除订单编号保存在：

```text
reports/created_order_ids.json
```

## 项目价值

该项目覆盖性能场景设计、负载模型实现、测试数据管理、指标监控、瓶颈定位、连接池调优和结果分析，形成了完整的性能测试闭环。