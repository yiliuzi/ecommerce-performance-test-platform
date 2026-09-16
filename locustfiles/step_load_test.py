from locust import HttpUser, LoadTestShape, between, events, task


MAX_FAILURE_RATIO = 0.01
MAX_P95_RESPONSE_TIME = 500


class EcommerceApiUser(HttpUser):
    """模拟用户持续访问电商核心接口。"""

    wait_time = between(0.2, 0.8)

    @task(1)
    def visit_health_api(self) -> None:
        """访问健康检查接口。"""
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
        """查询商品列表，模拟主要业务流量。"""
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

            if not isinstance(response_data, dict):
                response.failure("商品列表响应不是JSON对象")
                return

            product_items = response_data.get("items")

            if not isinstance(product_items, list):
                response.failure("商品列表响应缺少有效的items数组")
                return

            response.success()


class StepLoadShape(LoadTestShape):
    """
    阶梯式增加并发用户。

    0～30秒：10个用户
    30～60秒：30个用户
    60～90秒：60个用户
    90～120秒：100个用户
    """

    stages = [
        {
            "duration": 30,
            "users": 10,
            "spawn_rate": 5,
        },
        {
            "duration": 60,
            "users": 30,
            "spawn_rate": 10,
        },
        {
            "duration": 90,
            "users": 60,
            "spawn_rate": 15,
        },
        {
            "duration": 120,
            "users": 100,
            "spawn_rate": 20,
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


@events.quitting.add_listener
def check_performance_thresholds(environment, **kwargs) -> None:
    """测试结束时检查总体性能指标。"""
    total_stats = environment.stats.total

    total_requests = total_stats.num_requests
    total_failures = total_stats.num_failures
    failure_ratio = total_stats.fail_ratio
    average_response_time = total_stats.avg_response_time
    p95_response_time = total_stats.get_response_time_percentile(0.95)
    p99_response_time = total_stats.get_response_time_percentile(0.99)
    requests_per_second = total_stats.total_rps

    print("\n========== 阶梯加压测试结果 ==========")
    print(f"总请求数：{total_requests}")
    print(f"失败请求数：{total_failures}")
    print(f"失败率：{failure_ratio:.2%}")
    print(f"平均响应时间：{average_response_time:.2f} ms")
    print(f"P95响应时间：{p95_response_time:.2f} ms")
    print(f"P99响应时间：{p99_response_time:.2f} ms")
    print(f"平均RPS：{requests_per_second:.2f}")
    print("====================================")

    failed_reasons: list[str] = []

    if failure_ratio > MAX_FAILURE_RATIO:
        failed_reasons.append(
            f"失败率 {failure_ratio:.2%} 超过阈值 "
            f"{MAX_FAILURE_RATIO:.2%}"
        )

    if p95_response_time > MAX_P95_RESPONSE_TIME:
        failed_reasons.append(
            f"P95响应时间 {p95_response_time:.2f} ms 超过阈值 "
            f"{MAX_P95_RESPONSE_TIME} ms"
        )

    if failed_reasons:
        print("\n阶梯加压测试未通过：")
        for reason in failed_reasons:
            print(f"- {reason}")

        environment.process_exit_code = 1
    else:
        print("\n阶梯加压测试通过：所有指标均满足阈值。")
        environment.process_exit_code = 0