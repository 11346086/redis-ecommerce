from config_redis import get_redis_client

r = get_redis_client()

def delete_by_pattern(pattern):
    keys = r.keys(pattern)
    if not keys:
        return
    print(f"刪除 {pattern} 共 {len(keys)} 筆")
    for k in keys:
        r.delete(k)

if __name__ == "__main__":
    # 使用者資料
    delete_by_pattern("user:*")
    delete_by_pattern("cart:*")

    # 訂單相關
    delete_by_pattern("order:*")
    delete_by_pattern("user:*:orders")
    delete_by_pattern("queue:orders")

    # 搶購紀錄（如果也想清）
    delete_by_pattern("seckill:order:*")
    delete_by_pattern("user:*:seckill_orders")
    delete_by_pattern("seckill:users:*")
    delete_by_pattern("seckill:stock:*")

    print("清除完成！")
