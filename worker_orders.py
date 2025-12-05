import time
from datetime import datetime

from config_redis import get_redis_client

r = get_redis_client()

QUEUE_KEY = "queue:orders"


def process_order(order_id: str):
    order_key = f"order:{order_id}"
    order = r.hgetall(order_key)
    if not order:
        print(f"[{datetime.now()}] 找不到訂單 {order_id}，可能已被刪除。")
        return

    print(f"\n[{datetime.now()}] 開始處理訂單 {order_id} ...")
    print(f"  使用者：{order.get('user_id')}")
    print(f"  金額：${order.get('total')}")

    # 模擬花一點時間處理（例如寄信）
    time.sleep(1)

    # 更新訂單狀態
    r.hset(order_key, "status", "processed")
    r.hset(order_key, "processed_at", datetime.now().isoformat(timespec="seconds"))

    print(f"[{datetime.now()}] 訂單 {order_id} 處理完成，狀態改為 processed")


def main():
    print(f"訂單 worker 啟動，等待處理佇列：{QUEUE_KEY} ...")
    while True:
        # BLPOP：如果 queue 裡沒東西就會在這裡卡住，等有新訂單
        _, order_id = r.blpop(QUEUE_KEY)
        process_order(order_id)


if __name__ == "__main__":
    main()
