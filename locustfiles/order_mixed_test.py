import json
import random
from collections import deque
from pathlib import Path

from locust import HttpUser, between, events, task


USER_ID = 19

# 只选择库存相对充足的商品
PRODUCT_IDS = [56, 59, 55]

MAX_FAILURE_RATIO = 0.01
MAX_P95_RESPONSE_TIME = 800

# 保存本轮测试创建的订单ID
created_order_ids: deque[int] = deque(maxlen=5000)


class EcommerceOrderUser(HttpUser):
    """
    模拟电商系统中的混合业务流量。

    业务比例：
    80% 查询商品
    15% 查询订单详情
    5% 创建订单
    """

    wait_time = between(0.5, 1.5)

    @task(16)
    def get_product_list(self) -> None:
        """查询商品列表。"""
        with self.client.get(
            "/api/products",
            name="01 GET /api/products",
            catch_response=True,
        ) as response:
            if response.status_code != 200:
                response.failure(
                    f"商品列表查询失败，状态码：{response.status_code}"
                )
                return

            try:
                response_data = response.json()
            except ValueError:
                response.failure("商品列表响应不是合法JSON")
                return

            product_items = response_data.get("items")

            if not isinstance(product_items, list):
                response.failure("商品列表响应缺少有效的items数组")
                return

            response.success()

    @task(3)
    def get_order_detail(self) -> None:
        """从本轮创建的订单中随机查询一个订单。"""
        if not created_order_ids:
            return

        order_id = random.choice(list(created_order_ids))

        with self.client.get(
            f"/api/orders/{order_id}",
            name="02 GET /api/orders/{order_id}",
            catch_response=True,
        ) as response:
            if response.status_code != 200:
                response.failure(
                    f"订单查询失败：order_id={order_id}，"
                    f"状态码={response.status_code}"
                )
                return

            try:
                response_data = response.json()
            except ValueError:
                response.failure("订单详情响应不是合法JSON")
                return

            if response_data.get("id") != order_id:
                response.failure(
                    f"订单ID不一致：请求={order_id}，"
                    f"响应={response_data.get('id')}"
                )
                return

            if response_data.get("user_id") != USER_ID:
                response.failure(
                    f"订单用户ID错误：{response_data.get('user_id')}"
                )
                return

            if not isinstance(response_data.get("items"), list):
                response.failure("订单详情缺少有效的items数组")
                return

            response.success()

    @task(1)
    def create_order(self) -> None:
        """随机选择一个商品创建订单。"""
        product_id = random.choice(PRODUCT_IDS)

        request_body = {
            "user_id": USER_ID,
            "items": [
                {
                    "product_id": product_id,
                    "quantity": 1,
                }
            ],
        }

        with self.client.post(
            "/api/orders",
            json=request_body,
            name="03 POST /api/orders",
            catch_response=True,
        ) as response:
            if response.status_code != 201:
                response.failure(
                    f"创建订单失败：product_id={product_id}，"
                    f"状态码={response.status_code}，"
                    f"响应={response.text[:200]}"
                )
                return

            try:
                response_data = response.json()
            except ValueError:
                response.failure("创建订单响应不是合法JSON")
                return

            order_id = response_data.get("id")
            response_user_id = response_data.get("user_id")
            order_items = response_data.get("items")

            if not isinstance(order_id, int):
                response.failure(
                    f"订单响应缺少有效id：{order_id}"
                )
                return

            if response_user_id != USER_ID:
                response.failure(
                    f"订单用户ID错误：{response_user_id}"
                )
                return

            if not isinstance(order_items, list) or not order_items:
                response.failure("订单响应缺少商品明细")
                return

            created_order_ids.append(order_id)
            response.success()


@events.test_start.add_listener
def on_test_start(environment, **kwargs) -> None:
    """测试开始时清空上一轮保存在内存中的订单ID。"""
    created_order_ids.clear()

    print("\n========== 订单混合场景测试 ==========")
    print(f"测试用户ID：{USER_ID}")
    print(f"测试商品ID：{PRODUCT_IDS}")
    print("业务比例：查询商品80%，查询订单15%，创建订单5%")
    print("======================================")


@events.quitting.add_listener
def on_test_quitting(environment, **kwargs) -> None:
    """保存订单ID，并检查性能阈值。"""
    report_directory = Path("reports")
    report_directory.mkdir(parents=True, exist_ok=True)

    order_id_file = report_directory / "created_order_ids.json"
    order_id_file.write_text(
        json.dumps(
            list(created_order_ids),
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    total_stats = environment.stats.total

    total_requests = total_stats.num_requests
    total_failures = total_stats.num_failures
    failure_ratio = total_stats.fail_ratio
    average_response_time = total_stats.avg_response_time
    p95_response_time = (
        total_stats.get_response_time_percentile(0.95)
    )
    p99_response_time = (
        total_stats.get_response_time_percentile(0.99)
    )
    requests_per_second = total_stats.total_rps

    print("\n========== 混合场景测试结果 ==========")
    print(f"总请求数：{total_requests}")
    print(f"失败请求数：{total_failures}")
    print(f"失败率：{failure_ratio:.2%}")
    print(f"平均响应时间：{average_response_time:.2f} ms")
    print(f"P95响应时间：{p95_response_time:.2f} ms")
    print(f"P99响应时间：{p99_response_time:.2f} ms")
    print(f"平均RPS：{requests_per_second:.2f}")
    print(f"成功创建订单数：{len(created_order_ids)}")
    print(f"订单ID文件：{order_id_file}")
    print("====================================")

    failed_reasons: list[str] = []

    if not created_order_ids:
        failed_reasons.append("测试期间没有成功创建任何订单")

    if failure_ratio > MAX_FAILURE_RATIO:
        failed_reasons.append(
            f"失败率 {failure_ratio:.2%} 超过阈值 "
            f"{MAX_FAILURE_RATIO:.2%}"
        )

    if p95_response_time > MAX_P95_RESPONSE_TIME:
        failed_reasons.append(
            f"P95响应时间 {p95_response_time:.2f} ms "
            f"超过阈值 {MAX_P95_RESPONSE_TIME} ms"
        )

    if failed_reasons:
        print("\n混合场景测试未通过：")
        for reason in failed_reasons:
            print(f"- {reason}")

        environment.process_exit_code = 1
    else:
        print("\n混合场景测试通过：所有指标均满足阈值。")
        environment.process_exit_code = 0