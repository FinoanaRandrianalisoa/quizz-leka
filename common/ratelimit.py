import time

from common.graphql.errors import RateLimitedError


class RedisRateLimiter:
    """Compteur glissant sur Redis avec retour `retry_after`.

    Les limites sont indépendantes par dimension (utilisateur et IP).
    """

    def __init__(self, client):
        self.client = client

    def check(self, key: str, limit: int, window_seconds: int, scope_key: str) -> None:
        now = int(time.time())
        window_start = now - window_seconds
        k = f"ratelimit:{scope_key}:{key}"

        with self.client.pipeline() as pipe:
            pipe.zremrangebyscore(k, 0, window_start)
            pipe.zcard(k)
            count = pipe.execute()[1]

        if count >= limit:
            oldest = self.client.zrange(k, 0, 0, withscores=True)
            retry_after = max(0, int(oldest[0][1]) + window_seconds - now)
            raise RateLimitedError(retry_after=retry_after)

        self.client.zadd(k, {str(now): now})
        self.client.expire(k, window_seconds)
