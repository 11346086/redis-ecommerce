import json
from datetime import datetime

from redis.exceptions import WatchError

from config_redis import get_redis_client

r = get_redis_client()

SECKILL_PRODUCT_ID = "2991"
SECKILL_STOCK_KEY = f"seckill:stock:{SECKILL_PRODUCT_ID}"
SECKILL_USERS_KEY = f"seckill:users:{SECKILL_PRODUCT_ID}"


def show_seckill_status():
    info = r.hgetall(f"product:{SECKILL_PRODUCT_ID}")
    stock = int(r.get(SECKILL_STOCK_KEY) or 0)
    success_count = r.scard(SECKILL_USERS_KEY)

    print("\n=== 秒殺活動狀態 ===")
    print(f"商品：{SECKILL_PRODUCT_ID} {info.get('name')}（原價 ${info.get('price')}）")
    print(f"秒殺剩餘名額：{stock}")
    print(f"目前成功人數：{success_count}")


def seckill_attempt(user_id: str):
    """
    執行一次秒殺嘗試：
    - 確保每個 user 只能成功一次
    - 確保庫存不會超賣（用 WATCH / MULTI / EXEC）
    """

    while True:
        try:
            with r.pipeline() as pipe:
                # 1) 監看庫存與成功名單
                pipe.watch(SECKILL_STOCK_KEY, SECKILL_USERS_KEY)

                # 2) 檢查是否已經搶過
                if pipe.sismember(SECKILL_USERS_KEY, user_id):
                    pipe.unwatch()
                    return "already"

                # 3) 檢查庫存
                stock_val = pipe.get(SECKILL_STOCK_KEY)
                stock = int(stock_val or 0)
                if stock <= 0:
                    pipe.unwatch()
                    return "soldout"

                # 4) 可以搶 → 開始交易
                pipe.multi()
                # 庫存 -1
                pipe.decr(SECKILL_STOCK_KEY)
                # 把 user 加進成功名單
                pipe.sadd(SECKILL_USERS_KEY, user_id)

                # （選擇性）建立一筆秒殺訂單紀錄
                order_id = datetime.now().strftime("SK%Y%m%d%H%M%S%f")
                order_key = f"seckill:order:{order_id}"
                order_data = {
                    "user_id": user_id,
                    "product_id": SECKILL_PRODUCT_ID,
                    "created_at": datetime.now().isoformat(timespec="seconds"),
                }
                pipe.hset(order_key, mapping=order_data)
                pipe.rpush("seckill:orders", order_id)

                pipe.execute()

                # 秒殺成功後發一則 Pub/Sub 通知
                notice = {
                    "type": "seckill_success",
                    "user_id": user_id,
                    "product_id": SECKILL_PRODUCT_ID,
                    "time": datetime.now().isoformat(timespec="seconds"),
                }
                r.publish("channel:seckill", json.dumps(notice, ensure_ascii=False))

                # 也寫一筆事件到 Stream
                r.xadd(
                    "stream:seckill",
                    {
                        "user_id": user_id,
                        "product_id": SECKILL_PRODUCT_ID,
                        "result": "success",
                    }
                )


                return "success"


        except WatchError:
            # 表示在我們準備 EXEC 的時候，有別人改了這些 key
            # → 重試一次（while 會再跑一次）
            continue

def show_success_users():
    print("\n=== 秒殺成功名單 ===")
    users = r.smembers(SECKILL_USERS_KEY)
    if not users:
        print("目前還沒有成功紀錄。")
        return

    for u in users:
        print(f"- {u}")


def show_seckill_orders():
    print("\n=== 秒殺訂單列表 ===")
    order_ids = r.lrange("seckill:orders", 0, -1)
    if not order_ids:
        print("目前沒有秒殺訂單。")
        return

    for oid in order_ids:
        key = f"seckill:order:{oid}"
        data = r.hgetall(key)
        user_id = data.get("user_id", "")
        pid = data.get("product_id", "")
        created_at = data.get("created_at", "")
        print(f"- {oid} / 使用者：{user_id} / 商品：{pid} / 時間：{created_at}")


def main():
    while True:
        print("\n=== 秒殺測試 CLI ===")
        print("1. 查看秒殺活動狀態")
        print("2. 嘗試秒殺")
        print("3. 查看秒殺成功名單")
        print("4. 查看秒殺訂單列表")
        print("0. 離開")

        choice = input("請選擇功能：").strip()

        if choice == "1":
            show_seckill_status()
        elif choice == "2":
            user_id = input("請輸入你的 user id（例如 u1, melody）：").strip()
            if not user_id:
                print("❌ user id 不可以是空的")
                continue

            result = seckill_attempt(user_id)
            if result == "success":
                print("✅ 恭喜！秒殺成功 🎉")
            elif result == "already":
                print("⚠️ 你已經搶購成功過一次了，不能重複搶。")
            elif result == "soldout":
                print("❌ 很可惜，名額已經被搶光了。")
            else:
                print("❌ 秒殺結果未知，請稍後再試。")
        elif choice == "3":
            show_success_users()
        elif choice == "4":
            show_seckill_orders()
        elif choice == "0":
            print("Bye ~")
            break
        else:
            print("請輸入 0 / 1 / 2 / 3 / 4")


if __name__ == "__main__":
    main()
