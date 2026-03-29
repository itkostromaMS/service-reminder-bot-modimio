import asyncio
import copy
import json
from datetime import date
from typing import Any

from redis.asyncio import Redis

from config import DATA_FILE, REDIS_URL, STORAGE_BACKEND

_DATA_KEY = "service-reminder-bot:data"
_lock = asyncio.Lock()
_redis_client: Redis | None = None


def _default_root() -> dict[str, Any]:
    return {"__meta__": {}}


def _normalize_root(data: Any) -> dict[str, Any]:
    if not isinstance(data, dict):
        return _default_root()

    data.setdefault("__meta__", {})
    return data


def _user_bucket(data: dict[str, Any], user_id: str) -> dict[str, Any]:
    bucket = data.setdefault(user_id, {})
    bucket.setdefault("services", [])
    bucket.setdefault("state", {})
    return bucket


async def _get_redis_client() -> Redis:
    global _redis_client

    if _redis_client is None:
        _redis_client = Redis.from_url(REDIS_URL, encoding="utf-8", decode_responses=True)

    return _redis_client


async def _load_data_unlocked() -> dict[str, Any]:
    if STORAGE_BACKEND == "redis":
        client = await _get_redis_client()
        raw_data = await client.get(_DATA_KEY)
        if not raw_data:
            return _default_root()
        return _normalize_root(json.loads(raw_data))

    if not DATA_FILE.exists():
        return _default_root()

    with DATA_FILE.open("r", encoding="utf-8") as handle:
        return _normalize_root(json.load(handle))


async def _save_data_unlocked(data: dict[str, Any]) -> None:
    payload = json.dumps(data, ensure_ascii=False, indent=2)

    if STORAGE_BACKEND == "redis":
        client = await _get_redis_client()
        await client.set(_DATA_KEY, payload)
        return

    with DATA_FILE.open("w", encoding="utf-8") as handle:
        handle.write(payload)


async def _read_data(transform):
    async with _lock:
        data = await _load_data_unlocked()
        return transform(data)


async def _mutate_data(transform):
    async with _lock:
        data = await _load_data_unlocked()
        result = transform(data)
        await _save_data_unlocked(data)
        return result


def _service_copy(service: dict[str, Any]) -> dict[str, Any]:
    return copy.deepcopy(service)


def _parse_end_date(end_date: str | date) -> str:
    if isinstance(end_date, date):
        return end_date.isoformat()
    return str(end_date)


async def snapshot_data() -> dict[str, Any]:
    return await _read_data(lambda data: copy.deepcopy(data))


async def get_services(user_id: str) -> list[dict[str, Any]]:
    def transform(data: dict[str, Any]) -> list[dict[str, Any]]:
        services = _user_bucket(data, user_id).get("services", [])
        ordered = sorted(services, key=lambda item: (item.get("end_date", ""), item.get("id", 0)))
        return [_service_copy(service) for service in ordered]

    return await _read_data(transform)


async def get_service(user_id: str, service_id: int) -> dict[str, Any] | None:
    def transform(data: dict[str, Any]) -> dict[str, Any] | None:
        for service in _user_bucket(data, user_id).get("services", []):
            if service.get("id") == service_id:
                return _service_copy(service)
        return None

    return await _read_data(transform)


async def add_service(user_id: str, name: str, end_date: str | date) -> dict[str, Any]:
    def transform(data: dict[str, Any]) -> dict[str, Any]:
        bucket = _user_bucket(data, user_id)
        services = bucket["services"]
        next_id = max((service.get("id", 0) for service in services), default=0) + 1
        service = {
            "id": next_id,
            "name": name,
            "end_date": _parse_end_date(end_date),
            "notified_7": False,
            "notified_3": False,
            "notified_1": False,
            "notified_0": False,
            "created_at": date.today().isoformat(),
        }
        services.append(service)
        return _service_copy(service)

    return await _mutate_data(transform)


async def update_service_end_date(user_id: str, service_id: int, end_date: str | date) -> tuple[dict[str, Any], str] | tuple[None, None]:
    def transform(data: dict[str, Any]) -> tuple[dict[str, Any], str] | tuple[None, None]:
        for service in _user_bucket(data, user_id).get("services", []):
            if service.get("id") == service_id:
                previous = service["end_date"]
                service["end_date"] = _parse_end_date(end_date)
                service["notified_7"] = False
                service["notified_3"] = False
                service["notified_1"] = False
                service["notified_0"] = False
                return _service_copy(service), previous
        return None, None

    return await _mutate_data(transform)


async def mark_notified(user_id: str, service_id: int, days_key: int) -> bool:
    field_name = f"notified_{days_key}"

    def transform(data: dict[str, Any]) -> bool:
        for service in _user_bucket(data, user_id).get("services", []):
            if service.get("id") == service_id:
                service[field_name] = True
                return True
        return False

    return await _mutate_data(transform)


async def delete_service(user_id: str, service_id: int) -> dict[str, Any] | None:
    def transform(data: dict[str, Any]) -> dict[str, Any] | None:
        services = _user_bucket(data, user_id).get("services", [])
        for index, service in enumerate(services):
            if service.get("id") == service_id:
                removed = services.pop(index)
                return _service_copy(removed)
        return None

    return await _mutate_data(transform)


async def clear_services(user_id: str) -> int:
    def transform(data: dict[str, Any]) -> int:
        bucket = _user_bucket(data, user_id)
        count = len(bucket.get("services", []))
        bucket["services"] = []
        return count

    return await _mutate_data(transform)


async def get_user_state(user_id: str) -> dict[str, Any]:
    def transform(data: dict[str, Any]) -> dict[str, Any]:
        state = _user_bucket(data, user_id).get("state", {})
        return copy.deepcopy(state)

    return await _read_data(transform)


async def set_user_state(user_id: str, state: dict[str, Any]) -> dict[str, Any]:
    def transform(data: dict[str, Any]) -> dict[str, Any]:
        bucket = _user_bucket(data, user_id)
        bucket["state"] = copy.deepcopy(state)
        return copy.deepcopy(bucket["state"])

    return await _mutate_data(transform)


async def clear_user_state(user_id: str) -> None:
    def transform(data: dict[str, Any]) -> None:
        _user_bucket(data, user_id)["state"] = {}
        return None

    await _mutate_data(transform)


async def get_meta_value(key: str, default: Any = None) -> Any:
    def transform(data: dict[str, Any]) -> Any:
        meta = data.setdefault("__meta__", {})
        return copy.deepcopy(meta.get(key, default))

    return await _read_data(transform)


async def set_meta_value(key: str, value: Any) -> Any:
    def transform(data: dict[str, Any]) -> Any:
        meta = data.setdefault("__meta__", {})
        meta[key] = copy.deepcopy(value)
        return copy.deepcopy(value)

    return await _mutate_data(transform)