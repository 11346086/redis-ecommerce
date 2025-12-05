import json

from config_redis import get_redis_client

r = get_redis_client()


CHANNELS = ["channel:orders", "channel:seckill"]


def main():
    pubsub = r.pubsub()
    pubsub.subscribe(*CHANNELS)

    print("訂閱通知頻道中：", CHANNELS)
    print("有新事件會即時顯示在這裡。\n")

    for message in pubsub.listen():
        if message["type"] != "message":
            continue

        channel = message["channel"]
        data = message["data"]

        try:
            payload = json.loads(data)
        except Exception:
            payload = {"raw": data}

        print(f"[{channel}] 收到通知：{payload}")


if __name__ == "__main__":
    main()
