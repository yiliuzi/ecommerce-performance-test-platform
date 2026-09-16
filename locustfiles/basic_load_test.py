from locust import HttpUser, between, events, task


MAX_FAILURE_RATIO = 0.01
MAX_AVERAGE_RESPONSE_TIME = 200
MAX_P95_RESPONSE_TIME = 500


class EcommerceApiUser(HttpUser):
    """
    模拟普通用户访问电商接口。

    商品列表访问频率高于健康检查接口，
    以接近实际业务流量比例。
    """

    wait_time = between(1, 3)

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
                response.failure("健康检查响应不是合法 JSON")
                return

            if response_data.get("status") != "ok":
                response.failure(
                    f"健康检查状态异常：{response_data}"
                )
                return

            response.success()

    @task(3)
    def get_product_list(self) -> None:
        """查询商品列表。"""
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
                response.failure("商品列表响应不是合法 JSON")
                return

            if not isinstance(response_data, dict):
                response.failure("商品列表响应不是 JSON 对象")
                return

            if "items" not in response_data:
                response.failure("商品列表响应缺少 items 字段")
                return

            if not isinstance(response_data["items"], list):
                response.failure("商品列表的 items 字段不是数组")
                return

            response.success()


@events.quitting.add_listener
def check_performance_thresholds(environment, **kwargs) -> None:
    """
    测试结束时检查性能指标。

    任意指标不满足要求时，将进程退出码设置为1，
    便于后续接入GitHub Actions。
    """
    total_stats = environment.stats.total
    failed_reasons: list[str] = []

    failure_ratio = total_stats.fail_ratio
    average_response_time = total_stats.avg_response_time
    p95_response_time = total_stats.get_response_time_percentile(0.95)

    if failure_ratio > MAX_FAILURE_RATIO:
        failed_reasons.append(
            f"失败率 {failure_ratio:.2%} 超过阈值 "
            f"{MAX_FAILURE_RATIO:.2%}"
        )

    if average_response_time > MAX_AVERAGE_RESPONSE_TIME:
        failed_reasons.append(
            f"平均响应时间 {average_response_time:.2f} ms 超过阈值 "
            f"{MAX_AVERAGE_RESPONSE_TIME} ms"
        )

    if p95_response_time > MAX_P95_RESPONSE_TIME:
        failed_reasons.append(
            f"P95响应时间 {p95_response_time:.2f} ms 超过阈值 "
            f"{MAX_P95_RESPONSE_TIME} ms"
        )

    if failed_reasons:
        print("\n性能测试未通过：")
        for reason in failed_reasons:
            print(f"- {reason}")
        environment.process_exit_code = 1
    else:
        print("\n性能测试通过：所有指标均满足阈值。")
        environment.process_exit_code = 0