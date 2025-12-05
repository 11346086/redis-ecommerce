import redis

def get_redis_client():
    """
    回傳一個連到『雲端 Redis』的 client。
    把下面的 host / port / username / password 換成你 Redis Cloud 顯示的那一組。
    """
    return redis.Redis(
        host='redis-15228.c54.ap-northeast-1-2.ec2.cloud.redislabs.com',
        port=15228,
        username="default",
        password="kqGTtGBgEUkfpuFqPZ8aSelntMNqZC2v",                                    
        decode_responses=True,                                           
    )
