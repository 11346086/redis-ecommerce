from config_redis import get_redis_client

r = get_redis_client()


# 我們先清掉舊資料，避免之前測試的 key 造成干擾
def reset_data():
    keys = r.keys("product:*") + r.keys("stock:*")
    if keys:
        r.delete(*keys)
    print("已清除舊的商品 / 庫存資料。")

def seed_products():
    # 設計零食商品＋分類
    products = {
        # 類別：洋芋片
        "2001": {"name": "海苔洋芋片",       "price": 20, "category": "洋芋片"},
        "2002": {"name": "湖鹽洋芋片",       "price": 20, "category": "洋芋片"},
        "2003": {"name": "起司洋芋片",       "price": 20, "category": "洋芋片"},
        "2004": {"name": "香烤肋排洋芋片",   "price": 20, "category": "洋芋片"},
        "2005": {"name": "酸奶洋芋片",       "price": 59, "category": "洋芋片"},
        "2006": {"name": "BBQ洋芋片",        "price": 59, "category": "洋芋片"},

        # 類別：餅乾 / 曲奇
        "2101": {"name": "紫菜蘇打餅乾",     "price": 49, "category": "餅乾 / 曲奇"},
        "2102": {"name": "胡椒蘇打餅乾",     "price": 150, "category": "餅乾 / 曲奇"},
        "2103": {"name": "牛奶餅乾",         "price": 39, "category": "餅乾 / 曲奇"},
        "2104": {"name": "原味餅乾",         "price": 39, "category": "餅乾 / 曲奇"},
        "2105": {"name": "草莓法蘭酥",       "price": 70, "category": "餅乾 / 曲奇"},
        "2106": {"name": "巧克力法蘭酥",     "price": 70, "category": "餅乾 / 曲奇"},
        "2107": {"name": "牛奶法蘭酥",       "price": 70, "category": "餅乾 / 曲奇"},
        "2108": {"name": "咖啡法蘭酥",       "price": 70, "category": "餅乾 / 曲奇"},

        # 類別：糖果 / 巧克力
        "2201": {"name": "綜合水果軟糖",     "price": 69, "category": "糖果 / 巧克力"},
        "2202": {"name": "乖乖軟糖",         "price": 102, "category": "糖果 / 巧克力"},
        "2203": {"name": "牛奶糖",           "price": 18, "category": "糖果 / 巧克力"},
        "2204": {"name": "葡萄QQ巧克力球",   "price": 104, "category": "糖果 / 巧克力"},
        "2205": {"name": "薄荷巧克力",       "price": 65, "category": "糖果 / 巧克力"},
        "2206": {"name": "牛奶巧克力",       "price": 53, "category": "糖果 / 巧克力"},

        # 類別：泡麵 / 即食小點
        "2301": {"name": "鮮蝦魚板",         "price": 25, "category": "泡麵 / 即食小點"},
        "2302": {"name": "韓式泡菜",         "price": 25, "category": "泡麵 / 即食小點"},
        "2303": {"name": "蔥燒牛肉",         "price": 55, "category": "泡麵 / 即食小點"},
        "2304": {"name": "紅燒牛肉",         "price": 50, "category": "泡麵 / 即食小點"},
        "2305": {"name": "花雕雞",           "price": 60, "category": "泡麵 / 即食小點"},
        "2306": {"name": "排骨雞",           "price": 25, "category": "泡麵 / 即食小點"},
        "2307": {"name": "沖泡蘑菇濃湯",     "price": 39, "category": "泡麵 / 即食小點"},
        "2308": {"name": "沖泡南瓜濃湯",     "price": 39, "category": "泡麵 / 即食小點"},

        # 類別：飲料
        "2401": {"name": "紅茶",             "price": 25, "category": "飲料"},
        "2402": {"name": "綠茶",             "price": 25, "category": "飲料"},
        "2403": {"name": "蕎麥茶",           "price": 35, "category": "飲料"},
        "2404": {"name": "可爾必思",         "price": 30, "category": "飲料"},
        "2405": {"name": "黑松沙士",         "price": 20, "category": "飲料"},
        "2406": {"name": "可口可樂",         "price": 15, "category": "飲料"},

        # 類別：日/韓超夯零食
        "2501": {"name": "薯條三兄弟",       "price": 350, "category": "日/韓超夯零食"},
        "2502": {"name": "帆船餅乾",         "price": 65, "category": "日/韓超夯零食"},
        "2503": {"name": "味覺糖",           "price": 55, "category": "日/韓超夯零食"},
        "2504": {"name": "鹽味奶油可頌餅乾", "price": 50, "category": "日/韓超夯零食"},
        "2505": {"name": "低卡貝果餅乾",     "price": 85, "category": "日/韓超夯零食"},
        "2506": {"name": "ZERO水果軟糖",     "price": 75, "category": "日/韓超夯零食"},
    }

    # 給每個商品一些庫存
    stocks = {
        "2001": 20,
        "2002": 18,
        "2003": 15,
        "2004": 12,
        "2005": 10,
        "2006": 17,
        "2101": 10,
        "2102": 10,
        "2103": 15,
        "2104": 13,
        "2105": 11,
        "2106": 14,
        "2107": 14,
        "2108": 8,
        "2201": 11,
        "2202": 16,
        "2203": 12,
        "2204": 17,
        "2205": 17,
        "2206": 16,
        "2301": 8,
        "2302": 8,
        "2303": 10,
        "2304": 12,
        "2305": 15,
        "2306": 18,
        "2307": 19,
        "2308": 19,
        "2401": 18,
        "2402": 18,
        "2403": 15,
        "2404": 15,
        "2405": 12,
        "2406": 17,
        "2501": 10,
        "2502": 8,
        "2503": 10,
        "2504": 15,
        "2505": 9,
        "2506": 12,
    }

    product_details = {
        "2001": {
            "net_weight": "34g",
            "mfg": "2025-10-28",
            "exp": "2026-07-27",
            "origin": "台灣",
        },
        "2002": {
            "net_weight": "34g",
            "mfg": "2025-09-15",
            "exp": "2026-06-15",
            "origin": "台灣",
        },
        "2003": {
            "net_weight": "34g",
            "mfg": "2025-10-01",
            "exp": "2026-07-01",
            "origin": "台灣",
        },
        "2004": {
            "net_weight": "48g",
            "mfg": "2025-11-30",
            "exp": "2026-08-30",
            "origin": "台灣",
        },
        "2005": {
            "net_weight": "102g",
            "mfg": "2025-10-15",
            "exp": "2026-07-14",
            "origin": "台灣",
        },
        "2006": {
            "net_weight": "102g",
            "mfg": "2025-06-05",
            "exp": "2026-03-04",
            "origin": "台灣",
        },
        "2101": {
            "net_weight": "120g",
            "mfg": "2025-05-10",
            "exp": "2026-01-09",
            "origin": "台灣",
        },
        "2102": {
            "net_weight": "380g",
            "mfg": "2025-08-18",
            "exp": "2026-06-17",
            "origin": "台灣",
        },
        "2103": {
            "net_weight": "60g",
            "mfg": "2025-12-01",
            "exp": "2026-12-01",
            "origin": "台灣",
        },
        "2104": {
            "net_weight": "100g",
            "mfg": "2025-10-28",
            "exp": "2026-10-28",
            "origin": "台灣",
        },
        "2105": {
            "net_weight": "132g",
            "mfg": "2025-05-12",
            "exp": "2026-05-10",
            "origin": "台灣",
        },
        "2106": {
            "net_weight": "132g",
            "mfg": "2025-07-08",
            "exp": "2026-07-02",
            "origin": "台灣",
        },
        "2107": {
            "net_weight": "132g",
            "mfg": "2025-03-25",
            "exp": "2026-03-20",
            "origin": "台灣",
        },
        "2108": {
            "net_weight": "132g",
            "mfg": "2025-09-20",
            "exp": "2026-09-19",
            "origin": "台灣",
        },
        "2201": {
            "net_weight": "235g",
            "mfg": "2025-05-09",
            "exp": "2026-05-07",
            "origin": "台灣",
        },
        "2202": {
            "net_weight": "300g",
            "mfg": "2025-03-03",
            "exp": "2026-03-03",
            "origin": "台灣",
        },
        "2203": {
            "net_weight": "48g",
            "mfg": "2025-10-12",
            "exp": "2027-10-12",
            "origin": "台灣",
        },
        "2204": {
            "net_weight": "135g",
            "mfg": "2025-04-21",
            "exp": "2026-04-20",
            "origin": "台灣",
        },
        "2205": {
            "net_weight": "57g",
            "mfg": "2025-06-22",
            "exp": "2027-12-22",
            "origin": "美國",
        },
        "2206": {
            "net_weight": "50g",
            "mfg": "2025-12-01",
            "exp": "2026-06-01",
            "origin": "日本",
        },
        "2301": {
            "net_weight": "63g",
            "mfg": "2025-09-11",
            "exp": "2026-03-09",
            "origin": "台灣",
        },
        "2302": {
            "net_weight": "67g",
            "mfg": "2025-09-11",
            "exp": "2026-03-09",
            "origin": "台灣",
        },
        "2303": {
            "net_weight": "192g",
            "mfg": "2025-07-19",
            "exp": "2026-01-15",
            "origin": "台灣",
        },
        "2304": {
            "net_weight": "200g",
            "mfg": "2025-10-06",
            "exp": "2026-04-06",
            "origin": "台灣",
        },
        "2305": {
            "net_weight": "200g",
            "mfg": "2025-10-03",
            "exp": "2026-04-03",
            "origin": "台灣",
        },
        "2306": {
            "net_weight": "90g",
            "mfg": "2025-09-19",
            "exp": "2026-03-18",
            "origin": "台灣",
        },
        "2307": {
            "net_weight": "11g×3入/盒",
            "mfg": "2025-05-16",
            "exp": "2026-11-06",
            "origin": "台灣",
        },
        "2308": {
            "net_weight": "11g×3入/盒",
            "mfg": "2025-05-16",
            "exp": "2026-11-06",
            "origin": "台灣",
        },
        "2401": {
            "net_weight": "550ml",
            "mfg": "2025-06-06",
            "exp": "2026-04-02",
            "origin": "台灣",
        },
        "2402": {
            "net_weight": "550ml",
            "mfg": "2025-09-17",
            "exp": "2026-07-14",
            "origin": "台灣",
        },
        "2403": {
            "net_weight": "590ml",
            "mfg": "2025-09-15",
            "exp": "2026-07-12",
            "origin": "台灣",
        },
        "2404": {
            "net_weight": "310ml",
            "mfg": "2025-04-25",
            "exp": "2026-01-25",
            "origin": "台灣",
        },
        "2405": {
            "net_weight": "330ml",
            "mfg": "2025-05-21",
            "exp": "2026-02-21",
            "origin": "台灣",
        },
        "2406": {
            "net_weight": "250ml",
            "mfg": "2025-05-21",
            "exp": "2026-02-21",
            "origin": "台灣",
        },
        "2501": {
            "net_weight": "180g",
            "mfg": "2025-11-02",
            "exp": "2026-07-30",
            "origin": "日本",
        },
        "2502": {
            "net_weight": "59g",
            "mfg": "2025-08-05",
            "exp": "2026-08-05",
            "origin": "日本",
        },
        "2503": {
            "net_weight": "40g",
            "mfg": "2025-09-28",
            "exp": "2026-07-28",
            "origin": "日本",
        },
        "2504": {
            "net_weight": "55g",
            "mfg": "2025-08-30",
            "exp": "2026-08-30",
            "origin": "韓國",
        },
        "2505": {
            "net_weight": "60g",
            "mfg": "2025-09-30",
            "exp": "2026-06-30",
            "origin": "韓國",
        },
        "2506": {
            "net_weight": "48g",
            "mfg": "2025-01-27",
            "exp": "2026-01-27",
            "origin": "韓國",
        },
        
    }

    for pid, info in products.items():
        data = {
            "name": info["name"],
            "price": info["price"],
            "category": info["category"],
        }
        # 如果在 product_details 有設定，就把那些欄位一起加進來
        extra = product_details.get(pid, {})
        data.update(extra)

        # 寫進 Redis 的 hash：product:{pid}
        r.hset(f"product:{pid}", mapping=data)

    for pid, qty in stocks.items():
        # stock:{id} 用 string 存庫存數量
        r.set(f"stock:{pid}", qty)

    print("已建立測試商品與庫存：")
    for pid in products:
        name = products[pid]["name"]
        stock = r.get(f"stock:{pid}")
        print(f"- {pid} {name}，庫存：{stock}")

if __name__ == "__main__":
    reset_data()
    seed_products()
