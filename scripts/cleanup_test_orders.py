import json
import os
from collections import defaultdict
from pathlib import Path

import pymysql
from dotenv import load_dotenv


PROJECT_ROOT = Path(__file__).resolve().parent.parent
ORDER_ID_FILE = PROJECT_ROOT / "reports" / "created_order_ids.json"
ENV_FILE = PROJECT_ROOT / ".env"


def load_order_ids() -> list[int]:
    """读取本轮性能测试创建的订单ID。"""
    if not ORDER_ID_FILE.exists():
        raise FileNotFoundError(
            f"未找到订单ID文件：{ORDER_ID_FILE}"
        )

    file_content = ORDER_ID_FILE.read_text(encoding="utf-8")
    raw_order_ids = json.loads(file_content)

    if not isinstance(raw_order_ids, list):
        raise ValueError("订单ID文件内容必须是数组")

    order_ids = []

    for order_id in raw_order_ids:
        if isinstance(order_id, int) and order_id > 0:
            order_ids.append(order_id)

    # 去除重复ID，避免重复恢复库存
    return sorted(set(order_ids))


def create_connection():
    """创建MySQL数据库连接。"""
    load_dotenv(ENV_FILE)

    required_variables = [
        "DB_HOST",
        "DB_PORT",
        "DB_USER",
        "DB_PASSWORD",
        "DB_NAME",
    ]

    missing_variables = [
        variable
        for variable in required_variables
        if not os.getenv(variable)
    ]

    if missing_variables:
        raise ValueError(
            f"缺少数据库配置：{missing_variables}"
        )

    return pymysql.connect(
        host=os.environ["DB_HOST"],
        port=int(os.environ["DB_PORT"]),
        user=os.environ["DB_USER"],
        password=os.environ["DB_PASSWORD"],
        database=os.environ["DB_NAME"],
        charset="utf8mb4",
        autocommit=False,
        cursorclass=pymysql.cursors.DictCursor,
    )


def cleanup_test_orders() -> None:
    """
    删除本轮性能测试创建的订单，并恢复对应商品库存。

    操作顺序：
    1. 查询测试订单明细
    2. 汇总每个商品的购买数量
    3. 恢复商品库存
    4. 删除订单明细
    5. 删除订单主表记录
    6. 提交事务
    """
    order_ids = load_order_ids()

    if not order_ids:
        print("订单ID文件为空，没有需要清理的数据。")
        return

    placeholders = ", ".join(["%s"] * len(order_ids))
    connection = create_connection()

    try:
        with connection.cursor() as cursor:
            cursor.execute(
                f"""
                SELECT
                    order_id,
                    product_id,
                    quantity
                FROM order_items
                WHERE order_id IN ({placeholders})
                FOR UPDATE
                """,
                order_ids,
            )

            order_items = cursor.fetchall()

            if not order_items:
                print("数据库中未找到对应订单明细，无需清理。")
                return

            product_quantities: dict[int, int] = defaultdict(int)

            for item in order_items:
                product_quantities[item["product_id"]] += item["quantity"]

            print("准备恢复以下商品库存：")

            for product_id, quantity in product_quantities.items():
                print(
                    f"- product_id={product_id}，"
                    f"恢复数量={quantity}"
                )

                cursor.execute(
                    """
                    UPDATE products
                    SET stock = stock + %s
                    WHERE id = %s
                    """,
                    (quantity, product_id),
                )

                if cursor.rowcount != 1:
                    raise RuntimeError(
                        f"恢复商品库存失败：product_id={product_id}"
                    )

            cursor.execute(
                f"""
                DELETE FROM order_items
                WHERE order_id IN ({placeholders})
                """,
                order_ids,
            )
            deleted_order_items = cursor.rowcount

            cursor.execute(
                f"""
                DELETE FROM orders
                WHERE id IN ({placeholders})
                """,
                order_ids,
            )
            deleted_orders = cursor.rowcount

        connection.commit()

        # 清空文件，防止重复执行时再次恢复库存
        ORDER_ID_FILE.write_text(
            "[]\n",
            encoding="utf-8",
        )

        print("\n========== 清理完成 ==========")
        print(f"订单ID数量：{len(order_ids)}")
        print(f"删除订单数量：{deleted_orders}")
        print(f"删除订单明细数量：{deleted_order_items}")
        print("商品库存已经恢复")
        print("订单ID文件已经清空")
        print("=============================")

    except Exception:
        connection.rollback()
        print("清理失败，数据库事务已回滚。")
        raise

    finally:
        connection.close()


if __name__ == "__main__":
    cleanup_test_orders()