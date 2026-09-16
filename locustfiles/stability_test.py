from locust import (
    HttpUser,
    constant_pacing,
    events,
    task,
)


MAX_FAILURE_RATIO = 0.001
MAX_P95_RESPONSE_TIME = 500
MAX_P99_RESPONSE_TIME = 1000


class StabilityTestUser(HttpUser):
    """以稳定频率持续访问电商读取接口。"""

    # 每个虚拟用户大约每秒执行一次任务
    wait_time = constant_pacing(1.0)

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
        """持续查询商品列表。"""
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


@events.test_start.add_listener
def on_test_start(environment, **kwargs) -> None:
    print("\n========== 稳定性测试开始 ==========")
    print("并发用户：100")
    print("运行时间：5分钟")
    print("目标请求频率：约100 RPS")
    print("允许失败率：不超过0.1%")
    print("P95阈值：500 ms")
    print("P99阈值：1000 ms")
    print("==================================")


@events.quitting.add_listener
def check_stability_result(environment, **kwargs) -> None:
    """测试结束时检查稳定性指标。"""
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

    print("\n========== 稳定性测试结果 ==========")
    print(f"总请求数：{total_requests}")
    print(f"失败请求数：{total_failures}")
    print(f"失败率：{failure_ratio:.3%}")
    print(f"平均响应时间：{average_response_time:.2f} ms")
    print(f"P95响应时间：{p95_response_time:.2f} ms")
    print(f"P99响应时间：{p99_response_time:.2f} ms")
    print(f"最大响应时间：{max_response_time:.2f} ms")
    print(f"平均RPS：{requests_per_second:.2f}")
    print("==================================")

    failed_reasons: list[str] = []

    if failure_ratio > MAX_FAILURE_RATIO:
        failed_reasons.append(
            f"失败率 {failure_ratio:.3%} 超过阈值 "
            f"{MAX_FAILURE_RATIO:.3%}"
        )

    if p95_response_time > MAX_P95_RESPONSE_TIME:
        failed_reasons.append(
            f"P95 {p95_response_time:.2f} ms "
            f"超过阈值 {MAX_P95_RESPONSE_TIME} ms"
        )

    if p99_response_time > MAX_P99_RESPONSE_TIME:
        failed_reasons.append(
            f"P99 {p99_response_time:.2f} ms "
            f"超过阈值 {MAX_P99_RESPONSE_TIME} ms"
        )

    if failed_reasons:
        print("\n稳定性测试未通过：")

        for reason in failed_reasons:
            print(f"- {reason}")

        environment.process_exit_code = 1
    else:
        print("\n稳定性测试通过：持续负载下指标稳定。")
        environment.process_exit_code = 0