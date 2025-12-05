import redis

# 連到本機的 Redis（WSL 裡的 Redis 通常也可以用 localhost 連）
r = redis.Redis(
    host="localhost",
    port=6379,
    db=0,
    decode_responses=True,  # 自動把 bytes 轉成字串
)

try:
    pong = r.ping()
    print("✅ Redis 連線成功！ping 回應：", pong)

    # 試著寫入 / 讀取一個 key
    r.set("test:key", "hello redis from windows")
    value = r.get("test:key")
    print("讀到的值：", value)
except Exception as e:
    print("❌ 連線失敗，錯誤訊息：", e)
