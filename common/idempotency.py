import hashlib
import json

from common.graphql.errors import DuplicateIdempotencyKeyError, InvalidAmountError


class Idempotency:
    """Gestion des Idempotency-Key sur les mutations financières.

    Une même clé ne doit jamais produire deux effets : la première exécution
    enregistre la clé ; toute rediffusion de la même clé renvoie la même
    réponse déjà traitée ou est refusée.
    """

    def __init__(self, cache_client):
        self.client = cache_client

    def is_processed(self, key: str) -> bool:
        return self.client.exists(f"idem:{key}") == 1

    def mark(self, key: str, result: dict, ttl: int = 86400) -> None:
        self.client.set(f"idem:{key}", json.dumps(result), ex=ttl)

    def get(self, key: str):
        raw = self.client.get(f"idem:{key}")
        return json.loads(raw) if raw else None

    @staticmethod
    def fingerprint(operation: str, payload: dict) -> str:
        dump = json.dumps(payload, sort_keys=True, default=str)
        return hashlib.sha256((operation + dump).encode()).hexdigest()
