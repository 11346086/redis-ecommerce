from config_redis import get_redis_client

r = get_redis_client()


def print_stream(name: str, count: int = 10):
    print(f"\n=== Stream: {name} 最近 {count} 筆事件 ===")
    entries = r.xrevrange(name, count=count)
    if not entries:
        print("(沒有資料)")
        return
    for entry_id, fields in entries:
        print(f"- {entry_id} -> {fields}")


def main():
    print_stream("stream:orders", 10)
    print_stream("stream:seckill", 10)


if __name__ == "__main__":
    main()
