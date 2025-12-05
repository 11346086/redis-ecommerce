from config_redis import get_redis_client

r = get_redis_client()


# 多個秒殺商品及名額設定
SECKILL_STOCKS = {
    "2991": 5,  # 草莓夾心餅：名額 5
    "2992": 5,  # 巧克力夾心餅：名額 5
}

def seed_seckill():
    # 清掉之前所有秒殺資料
    keys = r.keys("seckill:*")
    if keys:
        r.delete(*keys)

    for pid, quota in SECKILL_STOCKS.items():
        stock_key = f"seckill:stock:{pid}"
        users_key = f"seckill:users:{pid}"

        r.set(stock_key, quota)
        r.delete(users_key)

        info = r.hgetall(f"product:{pid}")
        name = info.get("name", f"商品 {pid}")
        price = info.get("price", "?")

        print(f"已初始化秒殺設定：{pid} {name}（原價 ${price}），名額 {quota} 人")

if __name__ == "__main__":
    seed_seckill()
