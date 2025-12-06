from datetime import datetime
import json

from flask import Flask, render_template, redirect, url_for, request, flash
from redis.exceptions import WatchError
from config_redis import get_redis_client  

app = Flask(__name__)
app.secret_key = "dev-secret-key-please-change"  # 隨便一串字就好，用來支援 flash 訊息

# 改成使用共用的雲端 Redis 連線設定
r = get_redis_client()  

CURRENT_USER_ID = "user1"
CART_KEY = f"cart:{CURRENT_USER_ID}"


from datetime import datetime, time 

# 多個秒殺活動設定：key 是商品編號
SECKILL_EVENTS = {
    "2991": {  # 草莓夾心餅
        "start": time(10, 0),  # 10:00
        "end": time(11, 0),    # 11:00
    },
    "2992": {  # 巧克力夾心餅
        "start": time(14, 0),  # 14:00
        "end": time(15, 0),    # 15:00
    },
}

def is_seckill_open_for(product_id: str) -> bool:
    """判斷現在是否在某個商品的秒殺活動時間內。"""
    cfg = SECKILL_EVENTS.get(product_id)
    if not cfg:
        return False
    now = datetime.now().time()
    return cfg["start"] <= now <= cfg["end"]


def get_products_by_category():
    """從 Redis 抓出商品，依分類整理成 dict。"""
    product_keys = r.keys("product:*")
    if not product_keys:
        return {}

    product_ids = sorted(k.split(":")[1] for k in product_keys)
    products_by_cat = {}

    for pid in product_ids:
        info = r.hgetall(f"product:{pid}")
        if not info:
            continue
        stock = int(r.get(f"stock:{pid}") or 0)
        category = info.get("category", "未分類")

        # 👇很重要：限量商品只給秒殺用，不出現在一般商品列表
        if category == "限量商品":
            continue

        product_data = {
            "id": pid,
            "name": info.get("name"),
            "price": int(info.get("price", 0)),
            "stock": stock,
            "category": category,
            "image_url": f"images/products/{pid}.jpg",
        }

        products_by_cat.setdefault(category, []).append(product_data)

    return products_by_cat



def get_cart():
    """從 Redis 抓出購物車內容，整理成清單＋總金額。"""
    cart_items = r.hgetall(CART_KEY)
    items = []
    total = 0

    for pid, qty_str in cart_items.items():
        info = r.hgetall(f"product:{pid}")
        if not info:
            continue

        price = int(info.get("price", 0))
        qty = int(qty_str)
        stock = int(r.get(f"stock:{pid}") or 0)
        subtotal = price * qty
        total += subtotal

        items.append(
            {
                "id": pid,
                "name": info.get("name"),
                "price": price,
                "qty": qty,
                "stock": stock,
                "subtotal": subtotal,
            }
        )

    return items, total


def get_seckill_status_list():
    """取得所有秒殺活動的狀態（多個商品）。"""
    events = []

    for pid, cfg in SECKILL_EVENTS.items():
        info = r.hgetall(f"product:{pid}")
        product_name = info.get("name", f"商品 {pid}")
        price = info.get("price", "?")

        stock_key = f"seckill:stock:{pid}"
        users_key = f"seckill:users:{pid}"

        stock = int(r.get(stock_key) or 0)  # 剩餘名額
        success_users = sorted(list(r.smembers(users_key)))
        success_count = len(success_users)
        total_quota = success_count + stock  # 總名額

        open_now = is_seckill_open_for(pid)

        events.append(
            {
                "product_id": pid,
                "product_name": product_name,
                "price": price,
                "stock": stock,
                "success_count": success_count,
                "total_quota": total_quota,
                "start_time": cfg["start"].strftime("%H:%M"),
                "end_time": cfg["end"].strftime("%H:%M"),
                "open_now": open_now,
            }
        )

    # 可以照商品編號排序
    events.sort(key=lambda e: e["product_id"])
    return events


from redis.exceptions import WatchError  # 應該前面 checkout 那邊就有匯入了

def seckill_attempt(product_id: str, user_id: str) -> str:
    """
    嘗試參加某一個商品的秒殺。
    回傳字串結果：
      - "ok"
      - "no_quota"
      - "already_success"
    """
    stock_key = f"seckill:stock:{product_id}"
    users_key = f"seckill:users:{product_id}"

    try:
        with r.pipeline() as pipe:
            # 1) 監看庫存 & 成功名單
            pipe.watch(stock_key, users_key)

            stock = int(r.get(stock_key) or 0)
            if stock <= 0:
                pipe.unwatch()
                return "no_quota"

            if r.sismember(users_key, user_id):
                pipe.unwatch()
                return "already_success"

            # 2) 開始交易：扣名額 + 寫入成功名單 + 建立秒殺訂單
            pipe.multi()
            pipe.decr(stock_key)              # 名額 -1
            pipe.sadd(users_key, user_id)     # 成功名單加入

            # 建立秒殺訂單
            from datetime import datetime
            import json

            order_id = datetime.now().strftime("%Y%m%d%H%M%S%f")
            order_key = f"seckill:order:{order_id}"

            order_data = {
                "product_id": product_id,
                "user_id": user_id,
                "created_at": datetime.now().isoformat(timespec="seconds"),
            }

            pipe.hset(order_key, mapping=order_data)
            pipe.rpush("seckill:orders", order_id)

            pipe.execute()

        return "ok"

    except WatchError:
        # 有人同時在搶，導致 watch 的 key 被改動
        return "no_quota"


@app.route("/")
def index():
    # 進首頁就導到商品列表
    return redirect(url_for("products"))


@app.route("/products")
def products():
    # 從 Redis 抓商品，依類別分組
    products_by_category = get_products_by_category()
    categories_order = list(products_by_category.keys())

    return render_template(
        "products.html",
        products_by_category=products_by_category,  # 👈 名稱要跟樣板一致
        categories_order=categories_order,
        title="商品列表",
        subtitle="依商品分類顯示",
    )




@app.route("/add_to_cart", methods=["POST"])
def add_to_cart():
    """從商品列表加入購物車，會依庫存限制最大可加入數量。"""
    pid = request.form.get("product_id")
    qty_raw = request.form.get("qty", "1")

    if not pid:
        flash("商品資料有誤，請重新操作。", "error")
        return redirect(url_for("products"))

    # 轉成整數，避免有人亂塞字串
    try:
        qty = int(qty_raw)
    except ValueError:
        qty = 1
    if qty <= 0:
        qty = 1

    # 讀商品資訊與庫存
    info = r.hgetall(f"product:{pid}")
    if not info:
        flash("找不到該商品。", "error")
        return redirect(url_for("products"))

    name = info.get("name", pid)
    stock = int(r.get(f"stock:{pid}") or 0)

    # 已經在購物車裡的數量
    current_in_cart = int(r.hget(CART_KEY, pid) or 0)

    # 還能再放多少進購物車
    max_can_add = stock - current_in_cart

    if max_can_add <= 0:
        # 庫存都被購物車裡的數量用完了
        flash(f"{name} 庫存只剩 {stock}，購物車裡已經放到上限。", "error")
        return redirect(url_for("cart"))

    # 如果使用者輸入的數量比「可以再放的上限」還大，就自動調整
    if qty > max_can_add:
        qty = max_can_add
        flash(
            f"{name} 庫存剩 {stock}，購物車已有 {current_in_cart} 件，"
            f"最多再加 {max_can_add} 件，已自動幫你調整。",
            "error",
        )

    # 加入購物車
    r.hincrby(CART_KEY, pid, qty)
    flash(f"已將 {name} x {qty} 加入購物車。", "success")
    return redirect(url_for("cart"))

@app.route("/cart/update", methods=["POST"])
def cart_update():
    """在購物車中更新某個商品的數量（0 代表移除）。"""
    pid = request.form.get("product_id")
    qty_raw = request.form.get("qty", "1")

    if not pid:
        flash("商品資料有誤。", "error")
        return redirect(url_for("cart"))

    # 確認商品存在
    info = r.hgetall(f"product:{pid}")
    if not info:
        flash("找不到該商品。", "error")
        return redirect(url_for("cart"))
    name = info.get("name", pid)
    stock = int(r.get(f"stock:{pid}") or 0)

    # 把輸入的數量轉成整數
    try:
        qty = int(qty_raw)
    except ValueError:
        qty = 1

    # <=0 視為移除
    if qty <= 0:
        r.hdel(CART_KEY, pid)
        flash(f"已從購物車移除 {name}。", "success")
        return redirect(url_for("cart"))

    # 不可以超過庫存
    if qty > stock:
        qty = stock
        flash(f"{name} 庫存只有 {stock} 件，已幫你調整數量。", "error")

    # 直接設定新的數量（不是累加）
    r.hset(CART_KEY, pid, qty)
    flash(f"已更新 {name} 數量為 {qty}。", "success")
    return redirect(url_for("cart"))


@app.route("/cart/remove", methods=["POST"])
def cart_remove():
    """從購物車移除某個商品。"""
    pid = request.form.get("product_id")
    if not pid:
        flash("商品資料有誤。", "error")
        return redirect(url_for("cart"))

    name = r.hget(f"product:{pid}", "name") or pid
    r.hdel(CART_KEY, pid)
    flash(f"已從購物車移除 {name}。", "success")
    return redirect(url_for("cart"))


SHIPPING_THRESHOLD = 150   # 滿多少免運
SHIPPING_FEE = 60          # 未滿門檻的運費


@app.route("/cart")
def cart():
    """顯示購物車頁面。"""
    cart_data = r.hgetall(CART_KEY)

    items = []
    total = 0

    for pid, qty_str in cart_data.items():
        info = r.hgetall(f"product:{pid}")
        if not info:
            continue

        price = int(info.get("price", 0))
        qty = int(qty_str or 0)
        subtotal = price * qty
        total += subtotal

        items.append(
            {
                "id": pid,
                "name": info.get("name", ""),
                "price": price,
                "qty": qty,
                "subtotal": subtotal,
                "image": info.get("image", ""),
            }
        )

    # 運費計算：滿 150 免運，未滿收 60；如果購物車是空的就不用運費
    if total == 0:
        shipping_fee = 0
    elif total >= SHIPPING_THRESHOLD:
        shipping_fee = 0
    else:
        shipping_fee = SHIPPING_FEE

    grand_total = total + shipping_fee

    return render_template(
        "cart.html",
        items=items,
        total=total,
        shipping_fee=shipping_fee,
        grand_total=grand_total,
        SHIPPING_THRESHOLD=SHIPPING_THRESHOLD,
        title="購物車",
        subtitle="查看購物內容",
    )


@app.route("/checkout", methods=["POST"])
def checkout():
    cart_items = r.hgetall(CART_KEY)
    if not cart_items:
        flash("購物車是空的，無法結帳。", "error")
        return redirect(url_for("cart"))

    # 再算一次總金額
    _, total = get_cart()
    stock_keys = [f"stock:{pid}" for pid in cart_items.keys()]

    try:
        with r.pipeline() as pipe:
            # 1) 監看庫存
            pipe.watch(*stock_keys)

            # 2) 讀取目前庫存
            current_stocks = {}
            for pid in cart_items.keys():
                val = r.get(f"stock:{pid}")
                current_stocks[pid] = int(val or 0)

            # 3) 檢查庫存是否足夠
            shortage = []
            for pid, qty_str in cart_items.items():
                qty = int(qty_str)
                if current_stocks[pid] < qty:
                    shortage.append((pid, current_stocks[pid], qty))

            if shortage:
                pipe.unwatch()
                msg_lines = ["庫存不足，無法結帳："]
                for pid, have, need in shortage:
                    info = r.hgetall(f"product:{pid}")
                    name = info.get("name", pid)
                    msg_lines.append(f"{name} 需要 {need}，目前只有 {have}")
                flash("；".join(msg_lines), "error")
                return redirect(url_for("cart"))

            # 4) 開始交易：扣庫存 + 建訂單 + 清空購物車
            pipe.multi()

            # 扣庫存
            for pid, qty_str in cart_items.items():
                qty = int(qty_str)
                pipe.decrby(f"stock:{pid}", qty)

            # 建訂單 id
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

        # 交易成功後，丟進 queue，給 worker_orders.py 用（如果有開）
        r.rpush("queue:orders", order_id)

        flash(f"結帳成功！訂單編號：{order_id}", "success")
    except WatchError:
        flash("結帳過程中庫存被修改，請再試一次。", "error")

    return redirect(url_for("cart"))

@app.route("/seckill")
def seckill():
    """顯示多個秒殺活動頁面。"""
    events = get_seckill_status_list()
    return render_template(
        "seckill.html",
        title="限量秒殺活動",
        subtitle="不同商品有不同秒殺時段",
        events=events,
    )


@app.route("/seckill/join", methods=["POST"])
def seckill_join():
    """處理使用者秒殺嘗試（多商品版本）。"""
    product_id = request.form.get("product_id")
    user_id = request.form.get("user_id", "").strip()

    if not product_id or product_id not in SECKILL_EVENTS:
        flash("秒殺活動商品資料有誤。", "error")
        return redirect(url_for("seckill"))

    if not user_id:
        flash("請輸入 user id 再參加秒殺。", "error")
        return redirect(url_for("seckill"))

    # 檢查時間（只針對這個商品）
    from datetime import datetime
    if not is_seckill_open_for(product_id):
        flash("目前不在該商品的秒殺時間內，無法參加。", "error")
        return redirect(url_for("seckill"))

    result = seckill_attempt(product_id, user_id)

    if result == "ok":
        flash("恭喜秒殺成功！", "success")
    elif result == "no_quota":
        flash("名額已被搶光或同時競爭失敗，請再試試其他活動。", "error")
    elif result == "already_success":
        flash("你已經在本活動中搶購成功過一次囉。", "error")
    else:
        flash("秒殺時發生未知錯誤。", "error")

    return redirect(url_for("seckill"))


if __name__ == "__main__":
    # 開發階段用 debug=True 比較方便
    app.run(debug=True)
