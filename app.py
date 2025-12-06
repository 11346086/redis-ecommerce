from datetime import datetime, time, timedelta
import json
import uuid

from flask import Flask, render_template, redirect, url_for, request, flash, session
from redis.exceptions import WatchError
from config_redis import get_redis_client  

app = Flask(__name__)
app.secret_key = "dev-secret-key-please-change"  # 隨便一串字就好，用來支援 flash 訊息

# 改成使用共用的雲端 Redis 連線設定
r = get_redis_client()

def now_tw():
    """取得台灣現在時間（Render 用 UTC，所以手動 +8 小時）。"""
    return datetime.utcnow() + timedelta(hours=8)

def get_current_user_id():
    """從 session 取得目前使用者 id，沒有的話回傳 None。"""
    return session.get("user_id")


def get_cart_key():
    """每個使用者有自己的購物車 key。"""
    return f"cart:{get_current_user_id()}"

def require_user():
    """
    確保有 user_id，沒有的話回傳 (None, redirect_to_setup)
    有的話回傳 (user_id, None)
    在每個需要登入的 route 開頭用。
    """
    user_id = get_current_user_id()
    if not user_id:
        return None, redirect(url_for("profile_setup"))
    return user_id, None

def load_seckill_config():
    """從 Redis 讀所有搶購活動設定，回傳 dict: {pid: {'start': time, 'end': time}}"""
    events = {}
    for key in r.keys("seckill:event:*"):
        cfg = r.hgetall(key)
        pid = cfg.get("product_id")
        if not pid:
            continue

        start = cfg.get("start")
        end   = cfg.get("end")
        if not start or not end:
            continue

        try:
            sh, sm = [int(x) for x in start.split(":")]
            eh, em = [int(x) for x in end.split(":")]
            events[pid] = {
                "start": time(sh, sm),
                "end":   time(eh, em),
            }
        except Exception:
            continue

    return events


def is_seckill_open_for(product_id: str) -> bool:
    cfgs = load_seckill_config()
    cfg = cfgs.get(product_id)
    if not cfg:
        return False

    # 用台灣時間來判斷活動是否開放
    now = now_tw().time()
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

        # 👇很重要：限量商品只給搶購用，不出現在一般商品列表
        if category == "限量商品":
            continue

        product_data = {
            "id": pid,
            "name": info.get("name"),
            "price": int(info.get("price", 0)),
            "stock": stock,
            "category": category,
            "image_url": f"images/products/{pid}.jpg",
            
            "net_weight": info.get("net_weight"),
            "mfg": info.get("mfg"),
            "exp": info.get("exp"),
            "origin": info.get("origin"),
        }

        products_by_cat.setdefault(category, []).append(product_data)

    return products_by_cat



def get_cart():
    user_id, resp = require_user()
    if resp:
        return resp

    cart_key = f"cart:{user_id}"

    """從 Redis 抓出購物車內容，整理成清單＋總金額。"""
    cart_items = r.hgetall(cart_key)
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


# def get_seckill_status_list():
#     """取得所有搶購活動的狀態（多個商品）。"""
#     events = []

#     for pid, cfg in SECKILL_EVENTS.items():
#         info = r.hgetall(f"product:{pid}")
#         product_name = info.get("name", f"商品 {pid}")
#         price = info.get("price", "?")

#         stock_key = f"seckill:stock:{pid}"
#         users_key = f"seckill:users:{pid}"

#         stock = int(r.get(stock_key) or 0)  # 剩餘名額
#         success_users = sorted(list(r.smembers(users_key)))
#         success_count = len(success_users)
#         total_quota = success_count + stock  # 總名額

#         open_now = is_seckill_open_for(pid)

#         events.append(
#             {
#                 "product_id": pid,
#                 "product_name": product_name,
#                 "price": price,
#                 "stock": stock,
#                 "success_count": success_count,
#                 "total_quota": total_quota,
#                 "start_time": cfg["start"].strftime("%H:%M"),
#                 "end_time": cfg["end"].strftime("%H:%M"),
#                 "open_now": open_now,
#             }
#         )

#     # 可以照商品編號排序
#     events.sort(key=lambda e: e["product_id"])
#     return events

def get_seckill_status_list():
    """取得所有搶購活動狀態（從 Redis 設定來）。"""
    cfgs = load_seckill_config()
    events = []

    for pid, cfg in cfgs.items():
        info = r.hgetall(f"product:{pid}")
        product_name = info.get("name", f"商品 {pid}")
        price = info.get("price", "?")

        stock_key = f"seckill:stock:{pid}"
        users_key = f"seckill:users:{pid}"

        stock = int(r.get(stock_key) or 0)
        success_users = sorted(list(r.smembers(users_key)))
        success_count = len(success_users)
        total_quota = success_count + stock

        open_now = is_seckill_open_for(pid)

        events.append({
            "product_id": pid,
            "product_name": product_name,
            "price": price,
            "stock": stock,
            "success_count": success_count,
            "total_quota": total_quota,
            "start_time": cfg["start"].strftime("%H:%M"),
            "end_time": cfg["end"].strftime("%H:%M"),
            "open_now": open_now,
        })

    events.sort(key=lambda e: e["product_id"])
    return events


from redis.exceptions import WatchError  # 應該前面 checkout 那邊就有匯入了

def seckill_attempt(product_id: str, user_id: str) -> str:
    """
    嘗試參加某一個商品的搶購。
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

            # 2) 開始交易：扣名額 + 寫入成功名單 + 建立搶購訂單
            pipe.multi()
            pipe.decr(stock_key)              # 名額 -1
            pipe.sadd(users_key, user_id)     # 成功名單加入

            # 建立搶購訂單
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
            pipe.rpush(f"user:{user_id}:seckill_orders", order_id)

            pipe.execute()

        return "ok"

    except WatchError:
        # 有人同時在搶，導致 watch 的 key 被改動
        return "no_quota"


@app.route("/profile/setup", methods=["GET", "POST"])
def profile_setup():
    """
    首頁 / 註冊畫面：
    - GET：顯示歡迎標題 + 註冊表單 + 登入表單
    - POST：處理「註冊新帳號」
    """
    # 如果已經登入，就不要再註冊了，直接去商品列表
    if request.method == "GET" and get_current_user_id():
        return redirect(url_for("products"))

    if request.method == "POST":
        # 處理註冊（建立新 user）
        name = request.form.get("name", "").strip()
        phone = request.form.get("phone", "").strip()
        address = request.form.get("address", "").strip()

        if not name:
            flash("請輸入姓名。", "error")
            return redirect(url_for("profile_setup"))

        # 建一個簡單的 user_id
        user_id = "u_" + uuid.uuid4().hex[:8]

        # 把 user_id 放進 session，之後就能分辨誰是誰
        session["user_id"] = user_id

        # 存到 Redis：user:{user_id}
        r.hset(f"user:{user_id}", mapping={
            "name": name,
            "phone": phone,
            "address": address,
            "created_at": datetime.now().isoformat(timespec="seconds"),
        })

        flash("個人檔案建立完成，歡迎來逛逛～", "success")
        return redirect(url_for("products"))

    # GET：顯示首頁（歡迎 + 註冊 + 登入）
    return render_template(
        "profile_setup.html",
        title="🍬歡迎來到甜蜜魔法零食小舖🛒",
        subtitle="購買專屬你的療癒魔法！🪄✨",
    )

    # GET：顯示表單
    return render_template(
        "profile_setup.html",
        title="建立個人檔案",
        subtitle="先留下你的基本資料，再開始購物吧",
    )

@app.route("/login", methods=["POST"])
def login():
    """
    已有帳號的登入：
    - 使用者輸入 user_id
    - 確認 Redis 裡有這個 user
    - 設定 session["user_id"]
    """
    user_id = request.form.get("user_id", "").strip()

    if not user_id:
        flash("請輸入 user id。", "error")
        return redirect(url_for("profile_setup"))

    user_key = f"user:{user_id}"
    if not r.exists(user_key):
        flash("找不到這個 user id，請確認是否輸入正確。", "error")
        return redirect(url_for("profile_setup"))

    session["user_id"] = user_id
    flash("登入成功！", "success")
    return redirect(url_for("products"))


@app.route("/profile")
def profile():
    """顯示目前使用者的個人資料 + 歷史訂單 + 搶購活動紀錄。"""
    user_id, resp = require_user()
    if resp:
        return resp

    user_key = f"user:{user_id}"
    user_info = r.hgetall(user_key) or {}

    # ==== 歷史訂單：從 user:{user_id}:orders 撈出最近幾筆 ====
    orders_key = f"user:{user_id}:orders"
    order_ids = r.lrange(orders_key, 0, 19)  # 最多 20 筆，依你需求可調整

    orders = []
    for oid in order_ids:
        order_key = f"order:{oid}"
        od = r.hgetall(order_key)
        if not od:
            continue

        # 解析「商品金額小計」（checkout 時存的 total）
        try:
            items_total = int(od.get("total", 0))
        except ValueError:
            items_total = 0

        # 運費：跟 cart() 一樣的規則
        if items_total == 0:
            shipping_fee = 0
        elif items_total >= SHIPPING_THRESHOLD:
            shipping_fee = 0
        else:
            shipping_fee = SHIPPING_FEE

        grand_total = items_total + shipping_fee

        # 解析商品數量
        items_json = od.get("items", "{}")
        try:
            items_dict = json.loads(items_json)
        except json.JSONDecodeError:
            items_dict = {}
        items_count = sum(int(q) for q in items_dict.values() if str(q).isdigit())

        orders.append(
            {
                "id": oid,
                "items_total": items_total,      # 商品小計（純商品）
                "shipping_fee": shipping_fee,    # 運費
                "grand_total": grand_total,      # ✅ 含運費的應付金額
                "created_at": od.get("created_at", ""),
                "status": od.get("status", "已建立"),
                "items_count": items_count,
            }
        )

    # 讓最新的訂單排在最上面（前面 rpush 的話，預設會比較舊在前面）
    orders = list(reversed(orders))

    # ==== 搶購活動紀錄：user:{user_id}:seckill_orders ====
    seckill_list_key = f"user:{user_id}:seckill_orders"
    seckill_order_ids = r.lrange(seckill_list_key, 0, 19)  # 最多 20 筆

    seckill_records = []
    for soid in seckill_order_ids:
        skey = f"seckill:order:{soid}"
        sod = r.hgetall(skey)
        if not od:
            continue

        pid = sod.get("product_id")
        created_at = sod.get("created_at", "")

        # 商品名稱
        pinfo = r.hgetall(f"product:{pid}") if pid else {}
        pname = pinfo.get("name", f"商品 {pid}") if pid else f"商品 {pid}"

        seckill_records.append(
            {
                "order_id": soid,
                "product_id": pid,
                "product_name": pname,
                "created_at": created_at,
            }
        )

    # 讓最新的搶購紀錄排前面
    seckill_records = list(reversed(seckill_records))

    return render_template(
        "profile.html",
        title="個人檔案",
        subtitle="查看你的基本資料、歷史訂單與搶購紀錄",
        user_id=user_id,
        user=user_info,
        orders=orders,
        seckill_records=seckill_records,
    )

@app.route("/profile/edit", methods=["GET", "POST"])
def profile_edit():
    """編輯目前使用者的個人資料。"""
    user_id, resp = require_user()
    if resp:
        return resp

    user_key = f"user:{user_id}"

    if request.method == "POST":
        name = request.form.get("name", "").strip()
        phone = request.form.get("phone", "").strip()
        address = request.form.get("address", "").strip()

        if not name:
            flash("姓名不能空白。", "error")
            return redirect(url_for("profile_edit"))

        # 更新資料（保留原本的 created_at）
        existing = r.hgetall(user_key) or {}
        created_at = existing.get("created_at")

        data = {
            "name": name,
            "phone": phone,
            "address": address,
        }
        if created_at:
            data["created_at"] = created_at
        else:
            data["created_at"] = datetime.now().isoformat(timespec="seconds")

        data["updated_at"] = datetime.now().isoformat(timespec="seconds")

        r.hset(user_key, mapping=data)

        flash("個人資料已更新。", "success")
        return redirect(url_for("profile"))

    # GET：顯示編輯表單
    user_info = r.hgetall(user_key) or {}

    return render_template(
        "profile_edit.html",
        title="編輯個人檔案",
        subtitle="更新你的聯絡資訊與收件地址",
        user_id=user_id,
        user=user_info,
    )


@app.route("/orders/<order_id>")
def order_detail(order_id):
    """顯示單一訂單的明細內容。"""
    user_id, resp = require_user()
    if resp:
        return resp

    order_key = f"order:{order_id}"
    od = r.hgetall(order_key)
    if not od:
        flash("找不到這筆訂單。", "error")
        return redirect(url_for("profile"))

    # 確認這筆訂單是這個使用者的
    if od.get("user_id") != user_id:
        flash("你沒有權限查看這筆訂單。", "error")
        return redirect(url_for("profile"))

    # 解析 items（pid -> qty）
    items_json = od.get("items", "{}")
    try:
        items_dict = json.loads(items_json)
    except json.JSONDecodeError:
        items_dict = {}

    items = []
    items_total = 0
    for pid, qty_str in items_dict.items():
        try:
            qty = int(qty_str)
        except ValueError:
            qty = 0

        pinfo = r.hgetall(f"product:{pid}")
        if not pinfo:
            name = f"商品 {pid}"
            price = 0
        else:
            name = pinfo.get("name", f"商品 {pid}")
            try:
                price = int(pinfo.get("price", 0))
            except ValueError:
                price = 0

        subtotal = price * qty
        items_total += subtotal

        items.append(
            {
                "id": pid,
                "name": name,
                "price": price,
                "qty": qty,
                "subtotal": subtotal,
            }
        )

    # 運費：跟 cart() 使用相同規則
    if items_total == 0:
        shipping_fee = 0
    elif items_total >= SHIPPING_THRESHOLD:
        shipping_fee = 0
    else:
        shipping_fee = SHIPPING_FEE

    grand_total = items_total + shipping_fee

    # 如果之後你有把「應付金額」存進 hash，就可以這樣讀：
    # try:
    #     recorded_total = int(od.get("total", grand_total))
    # except ValueError:
    #     recorded_total = grand_total
    # 現在先不用也沒關係

    return render_template(
        "order_detail.html",
        title=f"訂單明細 #{order_id}",
        subtitle="查看此訂單的商品內容",
        order_id=order_id,
        order=od,
        items=items,
        items_total=items_total,
        shipping_fee=shipping_fee,
        grand_total=grand_total,
    )



@app.route("/")
def index():
    """
    首頁：
    - 如果已經登入（session 裡有 user_id）→ 直接去商品列表
    - 如果還沒有登入 → 去註冊 / 登入畫面（profile_setup）
    """
    if get_current_user_id():
        return redirect(url_for("products"))
    return redirect(url_for("profile_setup"))



@app.route("/products")
def products():
    # 確保一定有 user，沒有就會被導到 /profile/setup
    user_id, resp = require_user()
    if resp:
        return resp

    # 從 Redis 抓商品，依類別分組
    products_by_category = get_products_by_category()
    categories_order = list(products_by_category.keys())

    return render_template(
        "products.html",
        products_by_category=products_by_category,
        categories_order=categories_order,
        title="商品列表",
        subtitle="依商品分類顯示",
    )

@app.route("/add_to_cart", methods=["POST"])
def add_to_cart():
    user_id, resp = require_user()
    if resp:
        return resp

    cart_key = f"cart:{user_id}"

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
    current_in_cart = int(r.hget(cart_key, pid) or 0)

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
    r.hincrby(cart_key, pid, qty)
    flash(f"已將 {name} x {qty} 加入購物車。", "success")
    return redirect(url_for("cart"))

@app.route("/cart/update", methods=["POST"])
def cart_update():
    user_id, resp = require_user()
    if resp:
        return resp

    cart_key = f"cart:{user_id}"

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
        r.hdel(cart_key, pid)
        flash(f"已從購物車移除 {name}。", "success")
        return redirect(url_for("cart"))

    # 不可以超過庫存
    if qty > stock:
        qty = stock
        flash(f"{name} 庫存只有 {stock} 件，已幫你調整數量。", "error")

    # 直接設定新的數量（不是累加）
    r.hset(cart_key, pid, qty)
    flash(f"已更新 {name} 數量為 {qty}。", "success")
    return redirect(url_for("cart"))


@app.route("/cart/remove", methods=["POST"])
def cart_remove():
    user_id, resp = require_user()
    if resp:
        return resp

    cart_key = f"cart:{user_id}"

    """從購物車移除某個商品。"""
    pid = request.form.get("product_id")
    if not pid:
        flash("商品資料有誤。", "error")
        return redirect(url_for("cart"))

    name = r.hget(f"product:{pid}", "name") or pid
    r.hdel(cart_key, pid)
    flash(f"已從購物車移除 {name}。", "success")
    return redirect(url_for("cart"))


SHIPPING_THRESHOLD = 150   # 滿多少免運
SHIPPING_FEE = 60          # 未滿門檻的運費


@app.route("/cart")
def cart():
    user_id, resp = require_user()
    if resp:
        return resp

    cart_key = f"cart:{user_id}"

    """顯示購物車頁面。"""
    cart_data = r.hgetall(cart_key)

    items = []
    total = 0

    for pid, qty_str in cart_data.items():
        info = r.hgetall(f"product:{pid}")
        if not info:
            continue

        price = int(info.get("price", 0))
        qty = int(qty_str or 0)

        stock = int(r.get(f"stock:{pid}") or 0)

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
                "stock": stock,
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
    user_id, resp = require_user()
    if resp:
        return resp

    cart_key = f"cart:{user_id}"

    cart_items = r.hgetall(cart_key)
    if not cart_items:
        flash("購物車是空的，無法結帳。", "error")
        return redirect(url_for("cart"))

    # ✅ 直接在這裡重新計算總金額，不再呼叫 get_cart()
    total = 0
    for pid, qty_str in cart_items.items():
        info = r.hgetall(f"product:{pid}")
        if not info:
            continue
        price = int(info.get("price", 0))
        qty = int(qty_str or 0)
        total += price * qty

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

            # ✅ 這裡用「目前登入的 user_id」，不要再用 CURRENT_USER_ID
            order_data = {
                "user_id": user_id,
                "items": json.dumps(cart_items),
                "total": str(total),
                "status": "已建立",
                "created_at": datetime.now().isoformat(timespec="seconds"),
            }

            pipe.hset(order_key, mapping=order_data)
            # ✅ 每個使用者自己的訂單列表
            pipe.rpush(f"user:{user_id}:orders", order_id)

            # 清空購物車
            pipe.delete(cart_key)

            pipe.execute()

        # 交易成功後，丟進 queue，給 worker_orders.py 用（如果有開）
        r.rpush("queue:orders", order_id)

        flash(f"結帳成功！訂單編號：{order_id}", "success")
    except WatchError:
        flash("結帳過程中庫存被修改，請再試一次。", "error")

    return redirect(url_for("cart"))

@app.route("/seckill")
def seckill():
    """顯示多個搶購活動頁面（需先有 user）。"""
    user_id, resp = require_user()
    if resp:
        return resp

    events = get_seckill_status_list()

    # 撈出這個 user 的名字，畫面上可以顯示「目前登入：OOO」
    user_info = r.hgetall(f"user:{user_id}") or {}

    return render_template(
        "seckill.html",
        title="限量搶購活動",
        subtitle="不同商品有不同搶購時段",
        events=events,
        user_id=user_id,
        user=user_info,
    )

@app.route("/seckill/join", methods=["POST"])
def seckill_join():
    """處理使用者搶購嘗試（多商品版本），直接使用目前登入的 user。"""
    user_id, resp = require_user()
    if resp:
        return resp

    product_id = request.form.get("product_id")

    cfgs = load_seckill_config()
    if not product_id or product_id not in cfgs:
        flash("搶購活動商品資料有誤。", "error")
        return redirect(url_for("seckill"))

    # 檢查時間（只針對這個商品）
    if not is_seckill_open_for(product_id):
        flash("目前不在該商品的搶購時間內，無法參加。", "error")
        return redirect(url_for("seckill"))

    result = seckill_attempt(product_id, user_id)

    if result == "ok":
        flash("恭喜搶購成功！", "success")
    elif result == "no_quota":
        flash("名額已被搶光或同時競爭失敗，請再試試其他活動。", "error")
    elif result == "already_success":
        flash("你已經在本活動中搶購成功過一次囉。", "error")
    else:
        flash("搶購時發生未知錯誤。", "error")

    return redirect(url_for("seckill"))

@app.route("/logout")
def logout():
    session.pop("user_id", None)
    flash("已登出。", "success")
    return redirect(url_for("profile_setup"))



if __name__ == "__main__":
    # 開發階段用 debug=True 比較方便
    app.run(debug=True)
