from __future__ import annotations


class FakeRedisClient:
    def __init__(self) -> None:
        self.hashes: dict[str, dict[str, str]] = {}
        self.sorted_sets: dict[str, dict[str, float]] = {}
        self.lists: dict[str, list[str]] = {}
        self.key_values: dict[str, str] = {}
        self.streams: dict[str, list[tuple[str, dict[str, str]]]] = {}

    def ping(self):
        return True

    def hset(self, key, mapping):
        self.hashes.setdefault(key, {}).update({k: str(v) for k, v in mapping.items()})

    def hgetall(self, key):
        return dict(self.hashes.get(key, {}))

    def hget(self, key, field):
        return self.hashes.get(key, {}).get(field)

    def zadd(self, key, mapping):
        self.sorted_sets.setdefault(key, {}).update(mapping)

    def zrevrange(self, key, start, end):
        items = sorted(self.sorted_sets.get(key, {}).items(), key=lambda item: item[1], reverse=True)
        values = [member for member, _ in items]
        if end == -1:
            end = None
        return values[start:end]

    def lrange(self, key, start, end):
        values = self.lists.get(key, [])
        if end == -1:
            end = None
        return values[start:end]

    def rpush(self, key, value):
        self.lists.setdefault(key, []).append(value)

    def exists(self, key):
        return key in self.hashes or key in self.lists or key in self.key_values or key in self.sorted_sets

    def xadd(self, key, fields):
        stream = self.streams.setdefault(key, [])
        stream_id = f"{len(stream) + 1}-0"
        stream.append((stream_id, {k: str(v) for k, v in fields.items()}))
        return stream_id

    def xread(self, streams, count=None, block=None):
        results = []
        for key, last_id in streams.items():
            stream = self.streams.get(key, [])
            payloads = []
            for stream_id, fields in stream:
                if _stream_id_gt(stream_id, last_id):
                    payloads.append((stream_id, dict(fields)))
                    if count is not None and len(payloads) >= count:
                        break
            if payloads:
                results.append((key, payloads))
        return results

    def get(self, key):
        return self.key_values.get(key)

    def set(self, key, value):
        self.key_values[key] = value


def _stream_id_gt(left: str, right: str) -> bool:
    left_parts = [int(part) for part in left.split("-")]
    right_parts = [int(part) for part in right.split("-")]
    return tuple(left_parts) > tuple(right_parts)