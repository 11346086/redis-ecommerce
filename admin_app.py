import json
from datetime import time

from flask import Flask, render_template, redirect, url_for, request, flash, session
from functools import wraps
from config_redis import get_redis_client

app = Flask(__name__)
app.secret_key = "admin-secret-key-change-this"

# 共用同一顆雲端 Redis
r = get_redis_client()

# ================== 管理員帳密 ==================

ADMIN_USERNAME = "huixu"
ADMIN_PASSWORD = "huixu59"


def parse_time_hm(s: str):
    """'10:00' -> time(10,0)，錯誤回傳 None"""
    try:
        h, m = s.split(":")
        return time(int(h), int(m))
    except Exception:
        return None


def is_admin():
    return session.get("is_admin") is True


def admin_required(view_func):
    @wraps(view_func)
    def wrapper(*args, **kwargs):
        if not is_admin():
            flash("請先以管理員身分登入。", "error")
            # ⚠️ 這裡要用「函式名稱」，不是網址字串
            return redirect(url_for("admin_login"))
        return view_func(*args, **kwargs)

    return wrapper


# ================== 管理員登入 / 登出 ==================

@app.route("/", methods=["GET", "POST"])
def admin_login():
    """
    127.0.0.1:5001 一進來就是登入畫面
    """
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "").strip()

        if username == ADMIN_USERNAME and password == ADMIN_PASSWORD:
            session["is_admin"] = True
            flash("管理員登入成功。", "success")
            return redirect(url_for("admin_dashboard"))
        else:
            flash("帳號或密碼錯誤。", "error")

    return render_template(
        "admin_login.html",
        title="管理後台登入",
        subtitle="只有管理員可以使用的後台介面",
    )


@app.route("/admin/logout")
def admin_logout():
    session.pop("is_admin", None)
    flash("已登出管理員身分。", "success")
    return redirect(url_for("admin_login"))


# ================== 管理首頁 ==================

@app.route("/admin")
@admin_required
def admin_dashboard():
    product_count = len(r.keys("product:*"))
    order_count = len(r.keys("order:*"))
    user_count = len(r.keys("user:*"))

    return render_template(
        "admin_dashboard.html",
        title="管理後台",
        subtitle="快速查看系統概況",
        product_count=product_count,
        order_count=order_count,
        user_count=user_count,
    )


# ================== 商品管理 ==================

@app.route("/admin/products")
@admin_required
def admin_products():
    product_keys = r.keys("product:*")
    products = []

    for key in sorted(product_keys):
        pid = key.split(":")[1]
        info = r.hgetall(key)
        stock = int(r.get(f"stock:{pid}") or 0)

        products.append(
            {
                "id": pid,
                "name": info.get("name", ""),
                "price": int(info.get("price", 0)),
                "category": info.get("category", "未分類"),
                "stock": stock,
            }
        )

    return render_template(
        "admin_products.html",
        title="商品管理",
        subtitle="查看與調整商品資料",
        products=products,
    )


@app.route("/admin/products/new", methods=["GET", "POST"])
@admin_required
def admin_new_product():
    if request.method == "POST":
        pid = request.form.get("id", "").strip()
        name = request.form.get("name", "").strip()
        price_raw = request.form.get("price", "0").strip()
        category = request.form.get("category", "").strip() or "未分類"
        stock_raw = request.form.get("stock", "0").strip()

        if not pid or not name:
            flash("商品編號與名稱必填。", "error")
            return redirect(url_for("admin_new_product"))

        # 不可以重複
        if r.exists(f"product:{pid}"):
            flash(f"商品編號 {pid} 已存在。", "error")
            return redirect(url_for("admin_new_product"))

        try:
            price = int(price_raw)
            stock = int(stock_raw)
            if price < 0 or stock < 0:
                raise ValueError
        except ValueError:
            flash("價格與庫存必須是非負整數。", "error")
            return redirect(url_for("admin_new_product"))

        # 寫進 Redis
        data = {
            "name": name,
            "price": price,
            "category": category,
        }

        # 有填再存：淨重 / 產地 / 製造日 / 有效日
        for field in ["net_weight", "mfg", "exp", "origin"]:
            val = request.form.get(field, "").strip()
            if val:
                data[field] = val

        r.hset(f"product:{pid}", mapping=data)
        r.set(f"stock:{pid}", stock)

        flash(f"已新增商品 {pid} - {name}", "success")
        return redirect(url_for("admin_products"))

    # GET：顯示表單
    return render_template(
        "admin_product_new.html",
        title="新增商品",
        subtitle="建立新的商品資料",
    )


@app.route("/admin/products/<pid>/update", methods=["POST"])
@admin_required
def admin_update_product(pid):
    price_raw = request.form.get("price", "")
    stock_raw = request.form.get("stock", "")

    info = r.hgetall(f"product:{pid}")
    if not info:
        flash(f"找不到商品 {pid}", "error")
        return redirect(url_for("admin_products"))

    # 更新價格
    try:
        price = int(price_raw)
        if price < 0:
            raise ValueError
        r.hset(f"product:{pid}", "price", price)
    except ValueError:
        flash("價格必須是非負整數。", "error")

    # 更新庫存
    try:
        stock = int(stock_raw)
        if stock < 0:
            raise ValueError
        r.set(f"stock:{pid}", stock)
    except ValueError:
        flash("庫存必須是非負整數。", "error")

    flash(f"已更新商品 {pid} 的價格 / 庫存。", "success")
    return redirect(url_for("admin_products"))


# ================== 訂單管理 ==================

@app.route("/admin/orders")
@admin_required
def admin_orders():
    """列出所有訂單"""
    order_keys = r.keys("order:*")
    orders = []

    for key in sorted(order_keys):
        order_id = key.split(":")[1]
        data = r.hgetall(key)
        if not data:
            continue

        items_map = json.loads(data.get("items", "{}") or "{}")
        items_count = sum(int(q) for q in items_map.values()) if items_map else 0

        orders.append(
            {
                "id": order_id,
                "user_id": data.get("user_id", ""),
                "total": int(data.get("total", 0)),
                "status": data.get("status", ""),
                "created_at": data.get("created_at", ""),
                "items_count": items_count,
            }
        )

    # 讓最新的排在最上面
    orders.sort(key=lambda o: o["id"], reverse=True)

    return render_template(
        "admin_orders.html",
        title="訂單管理",
        subtitle="查看與管理所有訂單",
        orders=orders,
    )


@app.route("/admin/orders/<order_id>")
@admin_required
def admin_order_detail(order_id):
    """單筆訂單明細"""
    key = f"order:{order_id}"
    data = r.hgetall(key)
    if not data:
        flash(f"找不到訂單 {order_id}", "error")
        return redirect(url_for("admin_orders"))

    items_map = json.loads(data.get("items", "{}") or "{}")

    items = []
    for pid, qty_str in items_map.items():
        info = r.hgetall(f"product:{pid}")
        price = int(info.get("price", 0))
        qty = int(qty_str)
        items.append(
            {
                "id": pid,
                "name": info.get("name", pid),
                "price": price,
                "qty": qty,
                "subtotal": price * qty,
            }
        )

    total = int(data.get("total", 0))

    return render_template(
        "admin_order_detail.html",
        title=f"訂單 #{order_id}",
        subtitle="訂單詳細內容",
        order_id=order_id,
        order=data,
        items=items,
        total=total,
    )


@app.route("/admin/orders/<order_id>/status", methods=["POST"])
@admin_required
def admin_update_order_status(order_id):
    """修改訂單狀態（例如 created/paid/shipped...）"""
    new_status = request.form.get("status", "").strip()
    key = f"order:{order_id}"

    if not r.exists(key):
        flash(f"找不到訂單 {order_id}", "error")
    else:
        r.hset(key, "status", new_status)
        flash("已更新訂單狀態。", "success")

    return redirect(url_for("admin_order_detail", order_id=order_id))


# ================== 搶購管理 ==================

def get_seckill_admin_status():
    """
    給後台用的搶購活動狀態：
    - 每個商品的名額 / 已成功 / 剩餘名額
    - 成功紀錄：依搶購時間排序，顯示 user name + user id + 時間
    """
    events = []

    # 所有搶購訂單 id（建立訂單時有 rpush("seckill:orders", order_id)）
    all_order_ids = r.lrange("seckill:orders", 0, -1)

    # 1. 從 Redis 撈出所有 seckill:event:* 的設定
    for cfg_key in r.keys("seckill:event:*"):
        cfg = r.hgetall(cfg_key)
        pid = cfg.get("product_id")
        if not pid:
            continue

        start_str = cfg.get("start", "")   # 例如 "10:00"
        end_str   = cfg.get("end", "")     # 例如 "11:00"
        quota     = int(cfg.get("quota", 0) or 0)

        # 商品基本資訊
        info = r.hgetall(f"product:{pid}") or {}
        product_name = info.get("name", f"商品 {pid}")

        price_str = info.get("price", "0")
        try:
            price = int(price_str)
        except ValueError:
            price = 0

        # 活動剩餘名額（還在 seckill:stock:{pid} 裡）
        stock_key = f"seckill:stock:{pid}"
        stock = int(r.get(stock_key) or 0)

        # 2. 找出這個商品的所有成功紀錄
        success_records = []
        for oid in all_order_ids:
            order_key = f"seckill:order:{oid}"
            data = r.hgetall(order_key)
            if not data:
                continue

            # 只留下這個商品的訂單
            if data.get("product_id") != pid:
                continue

            user_id = data.get("user_id", "")
            created_at = data.get("created_at", "")

            # 去 user:{user_id} 撈使用者名稱
            user_info = r.hgetall(f"user:{user_id}") or {}
            user_name = user_info.get("name", user_id)

            success_records.append(
                {
                    "order_id": oid,
                    "user_id": user_id,
                    "user_name": user_name,
                    "time": created_at,
                }
            )

        # 依時間排序（越早搶到越前面）
        success_records.sort(key=lambda x: (x["time"] or "", x["order_id"]))

        success_count = len(success_records)

        events.append(
            {
                "product_id": pid,
                "product_name": product_name,
                "price": price,
                "stock": stock,              # 剩餘名額
                "success_count": success_count,
                "total_quota": quota,        # 原始名額
                "records": success_records,  # 給 template 用的成功名單
                "start_time": start_str,
                "end_time": end_str,
            }
        )

    # 依商品編號排序
    events.sort(key=lambda e: e["product_id"])
    return events



@app.route("/admin/seckill")
@admin_required
def admin_seckill():
    events = get_seckill_admin_status()
    return render_template(
        "admin_seckill.html",
        title="搶購管理",
        subtitle="查看搶購活動名額與成功名單",
        events=events,
    )


@app.route("/admin/seckill/new", methods=["GET", "POST"])
@admin_required
def admin_new_seckill():
    if request.method == "POST":
        pid       = request.form.get("product_id", "").strip()
        name      = request.form.get("product_name", "").strip()
        price_raw = request.form.get("price", "0").strip()
        start_str = request.form.get("start", "").strip()   # 例如 10:00
        end_str   = request.form.get("end", "").strip()     # 例如 11:00
        quota_raw = request.form.get("quota", "0").strip()

        # --- 基本欄位檢查 ---
        if not pid:
            flash("請輸入限量商品編號。", "error")
            return redirect(url_for("admin_new_seckill"))

        # 價格
        try:
            price = int(price_raw)
            if price < 0:
                raise ValueError
        except ValueError:
            flash("售價必須是非負整數。", "error")
            return redirect(url_for("admin_new_seckill"))

        # 如果 Redis 裡還沒有這個商品，就順便幫你建立一個「限量商品」
        product_key = f"product:{pid}"
        if not r.exists(product_key):
            if not name:
                name = f"限量商品 {pid}"

            r.hset(product_key, mapping={
                "name": name,
                "price": price,
                "category": "限量商品",   # 很重要：標成限量商品，前台一般商品不會顯示
            })
        else:
            # 商品已存在，如果有填新名稱或價格，就順便更新
            update_data = {"price": price}
            if name:
                update_data["name"] = name
            r.hset(product_key, mapping=update_data)

        # --- 解析開始 / 結束時間 ---
        start_t = parse_time_hm(start_str)
        end_t   = parse_time_hm(end_str)
        if not start_t or not end_t:
            flash("請輸入正確的開始 / 結束時間（例如 10:00）", "error")
            return redirect(url_for("admin_new_seckill"))

        # --- 解析名額 ---
        try:
            quota = int(quota_raw)
            if quota <= 0:
                raise ValueError
        except ValueError:
            flash("活動名額必須是正整數。", "error")
            return redirect(url_for("admin_new_seckill"))

        # --- 寫入這個商品的搶購設定（seckill:event:{pid}）---
        cfg_key = f"seckill:event:{pid}"
        r.hset(cfg_key, mapping={
            "product_id": pid,
            "start": start_str,
            "end": end_str,
            "quota": quota,
        })

        # --- 初始化搶購名額 & 清掉舊的成功名單 ---
        r.set(f"seckill:stock:{pid}", quota)
        r.delete(f"seckill:users:{pid}")

        flash(f"已建立商品 {pid} 的搶購活動。", "success")
        return redirect(url_for("admin_seckill"))

    # GET：只顯示表單
    return render_template(
        "admin_seckill_new.html",
        title="新增搶購活動",
        subtitle="設定活動商品、時間與名額",
    )

@app.route("/admin/seckill/<product_id>/edit", methods=["GET", "POST"])
@admin_required
def admin_edit_seckill(product_id):
    cfg_key = f"seckill:event:{product_id}"
    cfg = r.hgetall(cfg_key)
    if not cfg:
        flash(f"找不到商品 {product_id} 的搶購活動。", "error")
        return redirect(url_for("admin_seckill"))

    product_key = f"product:{product_id}"
    product = r.hgetall(product_key) or {}

    price_str = product.get("price", "0")
    try:
        current_price = int(price_str)
    except ValueError:
        current_price = 0

    if request.method == "POST":
        name      = request.form.get("product_name", "").strip()
        price_raw = request.form.get("price", "").strip()
        start_str = request.form.get("start", "").strip()
        end_str   = request.form.get("end", "").strip()
        quota_raw = request.form.get("quota", "0").strip()

        # 價格
        try:
            price = int(price_raw)
            if price < 0:
                raise ValueError
        except ValueError:
            flash("售價必須是非負整數。", "error")
            return redirect(url_for("admin_edit_seckill", product_id=product_id))

        # 時間
        start_t = parse_time_hm(start_str)
        end_t   = parse_time_hm(end_str)
        if not start_t or not end_t:
            flash("請輸入正確的開始 / 結束時間（例如 10:00）", "error")
            return redirect(url_for("admin_edit_seckill", product_id=product_id))

        # 名額
        try:
            quota = int(quota_raw)
            if quota <= 0:
                raise ValueError
        except ValueError:
            flash("活動名額必須是正整數。", "error")
            return redirect(url_for("admin_edit_seckill", product_id=product_id))

        # 更新商品資料
        update_data = {"price": price}
        if name:
            update_data["name"] = name
        if not product.get("category"):
            update_data["category"] = "限量商品"
        r.hset(product_key, mapping=update_data)

        # 更新活動設定
        r.hset(cfg_key, mapping={
            "product_id": product_id,
            "start": start_str,
            "end": end_str,
            "quota": quota,
        })

        # 重新計算剩餘名額：quota - 已成功人數
        success_count = int(r.scard(f"seckill:users:{product_id}") or 0)
        new_stock = max(quota - success_count, 0)
        r.set(f"seckill:stock:{product_id}", new_stock)

        flash(f"已更新商品 {product_id} 的搶購活動設定。", "success")
        return redirect(url_for("admin_seckill"))

    # GET：顯示編輯表單
    return render_template(
        "admin_seckill_edit.html",
        product_id=product_id,
        product=product,
        config=cfg,
        price=current_price,
        title="編輯搶購活動",
        subtitle="調整活動商品時間、名額與價格",
    )

@app.route("/admin/seckill/<pid>/update", methods=["POST"])
@admin_required
def admin_update_seckill(pid):
    """在搶購管理頁，直接修改售價 / 活動時間 / 名額。"""
    # 表單欄位
    price_raw = request.form.get("price", "").strip()
    start_str = request.form.get("start", "").strip()
    end_str   = request.form.get("end", "").strip()
    quota_raw = request.form.get("quota", "").strip()

    # 商品存在嗎？
    if not r.exists(f"product:{pid}"):
        flash(f"找不到商品 {pid}", "error")
        return redirect(url_for("admin_seckill"))

    # 秒殺活動設定存在嗎？
    cfg_key = f"seckill:event:{pid}"
    if not r.exists(cfg_key):
        flash(f"找不到商品 {pid} 的搶購活動設定。", "error")
        return redirect(url_for("admin_seckill"))

    # 解析時間
    start_t = parse_time_hm(start_str)
    end_t   = parse_time_hm(end_str)
    if not start_t or not end_t:
        flash("請輸入正確的開始 / 結束時間（例如 10:00）", "error")
        return redirect(url_for("admin_seckill"))

    # 解析價格 / 名額
    try:
        price = int(price_raw)
        quota = int(quota_raw)
        if price < 0 or quota <= 0:
            raise ValueError
    except ValueError:
        flash("售價必須是非負整數，名額必須是正整數。", "error")
        return redirect(url_for("admin_seckill"))

    # 目前已成功的人數（用 set 來算）
    success_users_key = f"seckill:users:{pid}"
    success_count = int(r.scard(success_users_key) or 0)

    # 剩餘名額 = 新總名額 - 已成功，最低 0
    remain = max(quota - success_count, 0)

    # 寫回 Redis
    # 1) 更新商品售價
    r.hset(f"product:{pid}", "price", price)

    # 2) 更新搶購活動設定
    r.hset(cfg_key, mapping={
        "product_id": pid,
        "start": start_str,
        "end":   end_str,
        "quota": quota,
    })

    # 3) 更新搶購剩餘名額
    r.set(f"seckill:stock:{pid}", remain)

    flash(f"已更新商品 {pid} 的搶購活動設定。", "success")
    return redirect(url_for("admin_seckill"))


if __name__ == "__main__":
    # 後台我幫你開在 5001 port，跟前台 5000 分開
    app.run(port=5001, debug=True)
