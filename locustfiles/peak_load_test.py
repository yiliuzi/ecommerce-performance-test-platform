from locust import (
    HttpUser,
    LoadTestShape,
    between,
    events,
    task,
)


MAX_FAILURE_RATIO = 0.01
MAX_P95_RESPONSE_TIME = 1000


class PeakTestUser(HttpUser):
    """模拟高并发读取商品数据的用户。"""

    wait_time = between(0.1, 0.5)

    @task(1)
    def visit_health_api(self) -> None:
        """请求健康检查接口。"""
        with self.client.get(
            "/health",
            name="GET /health",
            catch_response=True,
        ) as response:
            if response.status_code != 200:
                response.failure(
                    f"健康检查失败，状态码：{response.status_code}"
                )
                return

            try:
                response_data = response.json()
            except ValueError:
                response.failure("健康检查响应不是合法JSON")
                return

            if response_data.get("status") != "ok":
                response.failure(
                    f"健康检查状态异常：{response_data}"
                )
                return

            response.success()

    @task(4)
    def get_product_list(self) -> None:
        """高频查询商品列表。"""
        with self.client.get(
            "/api/products",
            name="GET /api/products",
            catch_response=True,
        ) as response:
            if response.status_code != 200:
                response.failure(
                    f"商品列表请求失败，状态码：{response.status_code}"
                )
                return

            try:
                response_data = response.json()
            except ValueError:
                response.failure("商品列表响应不是合法JSON")
                return

            product_items = response_data.get("items")

            if not isinstance(product_items, list):
                response.failure(
                    "商品列表响应缺少有效的items数组"
                )
                return

            response.success()


class PeakLoadShape(LoadTestShape):
    """
    峰值加压模型。

    每30秒提升一次压力：
    25 → 50 → 100 → 200 → 300用户。
    """

    stages = [
        {
            "duration": 30,
            "users": 25,
            "spawn_rate": 10,
        },
        {
            "duration": 60,
            "users": 50,
            "spawn_rate": 15,
        },
        {
            "duration": 90,
            "users": 100,
            "spawn_rate": 25,
        },
        {
            "duration": 120,
            "users": 200,
            "spawn_rate": 40,
        },
        {
            "duration": 150,
            "users": 300,
            "spawn_rate": 50,
        },
    ]

    def tick(self):
        run_time = self.get_run_time()

        for stage in self.stages:
            if run_time < stage["duration"]:
                return (
                    stage["users"],
                    stage["spawn_rate"],
                )

        return None


@events.test_start.add_listener
def on_test_start(environment, **kwargs) -> None:
    print("\n========== 峰值测试开始 ==========")
    print("用户阶段：25 → 50 → 100 → 200 → 300")
    print("每个阶段持续30秒")
    print("P95阈值：1000 ms")
    print("失败率阈值：1%")
    print("================================")


@events.quitting.add_listener
def check_peak_test_result(environment, **kwargs) -> None:
    """输出峰值测试结果并判断是否达到阈值。"""
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
    max_response_time = total_stats.max_response_time
    requests_per_second = total_stats.total_rps

    print("\n========== 峰值测试结果 ==========")
    print(f"总请求数：{total_requests}")
    print(f"失败请求数：{total_failures}")
    print(f"失败率：{failure_ratio:.2%}")
    print(f"平均响应时间：{average_response_time:.2f} ms")
    print(f"P95响应时间：{p95_response_time:.2f} ms")
    print(f"P99响应时间：{p99_response_time:.2f} ms")
    print(f"最大响应时间：{max_response_time:.2f} ms")
    print(f"平均RPS：{requests_per_second:.2f}")
    print("================================")

    failed_reasons: list[str] = []

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
        print("\n峰值测试未达到性能阈值：")

        for reason in failed_reasons:
            print(f"- {reason}")

        print(
            "注意：峰值测试未通过不代表代码运行错误，"
            "而是说明已经找到性能瓶颈。"
        )
        environment.process_exit_code = 1
    else:
        print("\n峰值测试通过：300用户下仍满足性能阈值。")
        environment.process_exit_code = 0