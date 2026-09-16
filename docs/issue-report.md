# 性能缺陷报告：高并发下数据库连接池耗尽

## 1. 缺陷基本信息

| 项目 | 内容 |
|---|---|
| 缺陷编号 | PERF-001 |
| 缺陷标题 | 300并发用户下数据库连接池耗尽导致商品接口返回HTTP 500 |
| 缺陷类型 | 性能/稳定性 |
| 严重程度 | Major |
| 优先级 | High |
| 缺陷状态 | 已优化，仍需继续跟踪 |
| 发现阶段 | 峰值性能测试 |
| 影响接口 | `GET /api/products` |
| 测试工具 | Locust 2.46.5 |

## 2. 测试环境

| 项目 | 配置 |
|---|---|
| 操作系统 | Windows |
| Python | 3.13.7 |
| API框架 | FastAPI |
| 数据库 | MySQL 8.0 |
| ORM | SQLAlchemy 2.x |
| 压测工具 | Locust |
| API地址 | `http://127.0.0.1:8000` |
| 并发用户 | 300 |

## 3. 前置条件

1. MySQL服务正常运行。
2. FastAPI服务运行在8000端口。
3. `/health`接口返回HTTP 200。
4. 数据库中存在有效商品数据。
5. Locust压测环境已安装完成。

## 4. 复现步骤

1. 启动MySQL服务。
2. 启动FastAPI服务：

```powershell
cd D:\Users\pc\api-database-test-platform
.\.venv\Scripts\Activate.ps1
python -m uvicorn app.main:app