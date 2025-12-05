from config_redis import get_redis_client

r = get_redis_client()



def list_products():
    print("\n=== 商品列表（Admin） ===")
    product_keys = r.keys("product:*")
    if not product_keys:
        print("目前沒有商品。")
        return

    product_ids = sorted(k.split(":")[1] for k in product_keys)

    for pid in product_ids:
        info = r.hgetall(f"product:{pid}")
        stock = r.get(f"stock:{pid}") or "0"
        print(f"{pid}. {info.get('name')} - ${info.get('price')} (庫存：{stock})")


def _get_next_product_id():
    product_keys = r.keys("product:*")
    if not product_keys:
        return "1001"
    ids = sorted(int(k.split(":")[1]) for k in product_keys)
    return str(ids[-1] + 1)


def add_product():
    print("\n=== 新增商品 ===")
    name = input("商品名稱：").strip()
    price_str = input("商品價格（整數）：").strip()
    stock_str = input("初始庫存（整數）：").strip()

    if not name:
        print("❌ 商品名稱不可為空")
        return
    if not price_str.isdigit() or int(price_str) < 0:
        print("❌ 價格必須是非負整數")
        return
    if not stock_str.isdigit() or int(stock_str) < 0:
        print("❌ 庫存必須是非負整數")
        return

    price = int(price_str)
    stock = int(stock_str)

    pid = _get_next_product_id()
    r.hset(f"product:{pid}", mapping={"name": name, "price": price})
    r.set(f"stock:{pid}", stock)

    print(f"✅ 已新增商品：{pid} {name} 價格：{price} 庫存：{stock}")


def update_price():
    print("\n=== 調整商品價格 ===")
    list_products()
    pid = input("請輸入要調整價格的商品編號：").strip()

    if not r.exists(f"product:{pid}"):
        print("❌ 找不到這個商品")
        return

    price_str = input("新價格（整數）：").strip()
    if not price_str.isdigit() or int(price_str) < 0:
        print("❌ 價格必須是非負整數")
        return

    price = int(price_str)
    r.hset(f"product:{pid}", "price", price)
    info = r.hgetall(f"product:{pid}")
    print(f"✅ 已更新 {pid} {info.get('name')} 的價格為 {price}")


def update_stock():
    print("\n=== 調整商品庫存（直接設定新的庫存數） ===")
    list_products()
    pid = input("請輸入要調整庫存的商品編號：").strip()

    stock_key = f"stock:{pid}"
    if not r.exists(f"product:{pid}"):
        print("❌ 找不到這個商品")
        return

    current_stock = int(r.get(stock_key) or 0)
    print(f"目前庫存：{current_stock}")

    stock_str = input("請輸入新的庫存數量（整數）：").strip()
    if not stock_str.isdigit() or int(stock_str) < 0:
        print("❌ 庫存必須是非負整數")
        return

    new_stock = int(stock_str)
    r.set(stock_key, new_stock)
    info = r.hgetall(f"product:{pid}")
    print(f"✅ 已將 {info.get('name')} 的庫存更新為 {new_stock}")


def list_all_orders():
    print("\n=== 所有訂單列表 ===")
    order_keys = r.keys("order:*")
    if not order_keys:
        print("目前沒有任何訂單。")
        return

    order_ids = sorted(k.split(":")[1] for k in order_keys)

    for oid in order_ids:
        key = f"order:{oid}"
        data = r.hgetall(key)
        user_id = data.get("user_id", "")
        total = data.get("total", "0")
        status = data.get("status", "unknown")
        created_at = data.get("created_at", "")
        print(f"- 訂單 {oid} / 使用者：{user_id} / 金額：${total} / 狀態：{status} / 建立時間：{created_at}")


def main():
    while True:
        print("\n=== Admin 管理介面 ===")
        print("1. 查看商品列表")
        print("2. 新增商品")
        print("3. 調整商品價格")
        print("4. 調整商品庫存")
        print("5. 查看所有訂單")
        print("0. 離開")

        choice = input("請選擇功能：").strip()

        if choice == "1":
            list_products()
        elif choice == "2":
            add_product()
        elif choice == "3":
            update_price()
        elif choice == "4":
            update_stock()
        elif choice == "5":
            list_all_orders()
        elif choice == "0":
            print("Bye Admin ~")
            break
        else:
            print("請輸入 0 / 1 / 2 / 3 / 4 / 5")


if __name__ == "__main__":
    main()
