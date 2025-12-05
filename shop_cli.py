import json
from datetime import datetime

from redis.exceptions import WatchError

from config_redis import get_redis_client

r = get_redis_client()


# 先假設只有一個使用者
CURRENT_USER_ID = "user1"
CART_KEY = f"cart:{CURRENT_USER_ID}"


def list_products():
    print("\n=== 商品列表 ===")
    product_keys = r.keys("product:*")
    if not product_keys:
        print("目前沒有商品，請先執行 seed_products.py")
        return

    product_ids = sorted(k.split(":")[1] for k in product_keys)

    for pid in product_ids:
        info = r.hgetall(f"product:{pid}")
        stock = r.get(f"stock:{pid}") or "0"
        print(f"{pid}. {info.get('name')} - ${info.get('price')} (庫存：{stock})")


def buy_one():
    # 這個函式保留當作「直接購買」示範
    list_products()
    pid = input("\n請輸入要購買的商品編號（例如 1001）：").strip()

    if not r.exists(f"product:{pid}"):
        print("❌ 找不到這個商品編號")
        return

    stock_key = f"stock:{pid}"
    stock = r.get(stock_key)

    if stock is None:
        print("❌ 這個商品尚未設定庫存")
        return

    stock = int(stock)
    if stock <= 0:
        print("❌ 庫存不足，無法購買")
        return

    new_stock = r.decr(stock_key)
    info = r.hgetall(f"product:{pid}")
    print(f"✅ 購買成功！已購買：{info.get('name')}")
    print(f"剩餘庫存：{new_stock}")


def add_to_cart():
    list_products()
    pid = input("\n請輸入要加入購物車的商品編號：").strip()

    if not r.exists(f"product:{pid}"):
        print("❌ 找不到這個商品編號")
        return

    qty_str = input("請輸入數量：").strip()
    if not qty_str.isdigit() or int(qty_str) <= 0:
        print("❌ 數量必須是正整數")
        return

    qty = int(qty_str)

    # 先不扣真正庫存，只是放到購物車
    r.hincrby(CART_KEY, pid, qty)

    info = r.hgetall(f"product:{pid}")
    print(f"✅ 已將 {info.get('name')} x {qty} 加入購物車！")


def view_cart():
    print("\n=== 購物車內容 ===")
    cart_items = r.hgetall(CART_KEY)

    if not cart_items:
        print("購物車是空的～")
        return

    total = 0
    for pid, qty_str in cart_items.items():
        info = r.hgetall(f"product:{pid}")
        if not info:
            continue  # 商品可能被刪掉了

        qty = int(qty_str)
        price = int(info.get("price", 0))
        subtotal = price * qty
        total += subtotal

        print(f"{pid}. {info.get('name')} x {qty} = ${subtotal}")

    print(f"\n購物車總金額：${total}")
    return total


def checkout():
    print("\n=== 結帳 ===")
    cart_items = r.hgetall(CART_KEY)
    if not cart_items:
        print("購物車是空的，無法結帳。")
        return

    # 先顯示一次購物車內容
    total = view_cart()
    if total is None:
        return

    confirm = input("\n確認結帳？(y/n)：").strip().lower()
    if confirm != "y":
        print("已取消結帳。")
        return

    stock_keys = [f"stock:{pid}" for pid in cart_items.keys()]

    try:
        with r.pipeline() as pipe:
            pipe.watch(*stock_keys)

            current_stocks = {}
            for pid in cart_items.keys():
                val = r.get(f"stock:{pid}")
                current_stocks[pid] = int(val or 0)

            shortage = []
            for pid, qty_str in cart_items.items():
                qty = int(qty_str)
                if current_stocks[pid] < qty:
                    shortage.append((pid, current_stocks[pid], qty))

            if shortage:
                pipe.unwatch()
                print("❌ 庫存不足，無法結帳：")
                for pid, have, need in shortage:
                    info = r.hgetall(f"product:{pid}")
                    name = info.get("name", pid)
                    print(f"- {name}（需要 {need}，目前只有 {have}）")
                return

            pipe.multi()

            # 扣庫存
            for pid, qty_str in cart_items.items():
                qty = int(qty_str)
                pipe.decrby(f"stock:{pid}", qty)

            # 建訂單
            order_id = datetime.now().strftime("%Y%m%d%H%M%S%f")
            order_key = f"order:{order_id}"

            order_data = {
                "user_id": CURRENT_USER_ID,
                "items": json.dumps(cart_items),
                "total": str(total),
                "status": "created",
                "created_at": datetime.now().isoformat(timespec="seconds"),
            }

            pipe.hset(order_key, mapping=order_data)
            pipe.rpush(f"user:{CURRENT_USER_ID}:orders", order_id)

            # 清空購物車
            pipe.delete(CART_KEY)

            pipe.execute()

            r.rpush("queue:orders", order_id)

        # 🔹 Transaction 成功之後：把訂單丟進「處理佇列」
        r.rpush("queue:orders", order_id)

        # 🔹 同時用 Pub/Sub 發布一則訂單建立通知
        notice = {
            "type": "order_created",
            "order_id": order_id,
            "user_id": CURRENT_USER_ID,
            "total": total,
        }
        r.publish("channel:orders", json.dumps(notice, ensure_ascii=False))

        # 🔹 將訂單建立事件寫入 Stream（事件紀錄）
        r.xadd(
            "stream:orders",
            {
                "order_id": order_id,
                "user_id": CURRENT_USER_ID,
                "total": str(total),
                "status": "created",
            }
        )

        print(f"✅ 結帳成功！訂單編號：{order_id}")

    except WatchError:
        print("⚠️ 結帳過程中庫存被其他人修改，請稍後再試。")

def view_orders():
    print("\n=== 歷史訂單 ===")
    orders_key = f"user:{CURRENT_USER_ID}:orders"
    order_ids = r.lrange(orders_key, 0, -1)

    if not order_ids:
        print("目前沒有任何訂單記錄。")
        return

    for order_id in order_ids:
        order_key = f"order:{order_id}"
        data = r.hgetall(order_key)
        if not data:
            continue

        created_at = data.get("created_at", "")
        total = data.get("total", "0")
        status = data.get("status", "unknown")

        print(f"- 訂單 {order_id}")
        print(f"  建立時間：{created_at}")
        print(f"  總金額：${total}")
        print(f"  狀態：{status}")
        print("")

    print("（註：訂單狀態後續可由 worker_orders.py 更新為 processed）")


def main():
    while True:
        print("\n=== 簡易購物 CLI ===")
        print("1. 查看商品列表")
        print("2. 購買一件商品（直接扣庫存，示範用）")
        print("3. 加入購物車")
        print("4. 查看購物車")
        print("5. 結帳（使用 Redis Transaction）")
        print("6. 查看歷史訂單")
        print("0. 離開")


        choice = input("請選擇功能：").strip()

        if choice == "1":
            list_products()
        elif choice == "2":
            buy_one()
        elif choice == "3":
            add_to_cart()
        elif choice == "4":
            view_cart()
        elif choice == "5":
            checkout()
        elif choice == "6": 
            view_orders()
        elif choice == "0":
            print("Bye ~")
            break
        else:
            print("請輸入 0 / 1 / 2 / 3 / 4 / 5 / 6")



if __name__ == "__main__":
    main()
