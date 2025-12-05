from config_redis import get_redis_client

r = get_redis_client()

try:
    pong = r.ping()
    print("✅ 連線成功，PING 回應：", pong)
    r.set("hello", "from cloud redis")
    print("讀回來：", r.get("hello"))
except Exception as e:
    print("❌ 連線失敗：", e)
