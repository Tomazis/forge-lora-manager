import hashlib
import json
import os
import struct
import threading

from lora_manager.constants import EMPTY_SHA256_PREFIX, HASH_CHUNK, MAX_SAFETENSORS_HEADER

_lock = threading.Lock()
_cache: dict | None = None


def _cache_file() -> str:
    try:
        from modules.paths_internal import data_path

        return os.path.join(data_path, "lora-manager-hashes.json")
    except Exception:
        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        return os.path.join(root, "lora-manager-hashes.json")


def _load_cache() -> dict:
    global _cache
    if _cache is not None:
        return _cache
    path = _cache_file()
    try:
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
        _cache = data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError):
        _cache = {}
    return _cache


def _save_cache():
    path = _cache_file()
    tmp = path + ".tmp"
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(_cache or {}, fh)
    os.replace(tmp, path)


def _stat_key(path: str) -> tuple[str, int, int]:
    st = os.stat(path)
    return os.path.normcase(os.path.abspath(path)), int(st.st_size), int(st.st_mtime)


def sha256_file(path: str) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(HASH_CHUNK), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_safetensors_metadata(path: str) -> dict:
    try:
        with open(path, "rb") as fh:
            header_len_bytes = fh.read(8)
            if len(header_len_bytes) < 8:
                return {}
            header_len = struct.unpack("<Q", header_len_bytes)[0]
            if header_len > MAX_SAFETENSORS_HEADER:
                return {}
            header_bytes = fh.read(header_len)
            if len(header_bytes) < header_len:
                return {}
            header = json.loads(header_bytes.decode("utf-8"))
            meta = header.get("__metadata__", {})
            return meta if isinstance(meta, dict) else {}
    except (OSError, json.JSONDecodeError, UnicodeDecodeError, struct.error, MemoryError):
        return {}


def autov3_from_header(path: str):
    if not path.lower().endswith(".safetensors"):
        return None
    meta = read_safetensors_metadata(path)
    raw = meta.get("sshs_model_hash") or meta.get("modelspec.hash_sha256")
    if not isinstance(raw, str):
        return None
    raw = raw.strip()
    if raw.lower().startswith("0x"):
        raw = raw[2:]
    if len(raw) < 12:
        return None
    value = raw[:12].lower()
    if value == EMPTY_SHA256_PREFIX:
        return None
    return value


def cached_hashes(path: str) -> dict | None:
    try:
        key_path, size, mtime = _stat_key(path)
    except OSError:
        return None
    cache_key = f"{key_path}|{size}|{mtime}"
    with _lock:
        hit = _load_cache().get(cache_key)
    if isinstance(hit, dict) and hit.get("sha256"):
        return hit
    return None


def hashes_for(path: str) -> dict:
    key_path, size, mtime = _stat_key(path)
    cache_key = f"{key_path}|{size}|{mtime}"
    with _lock:
        cache = _load_cache()
        hit = cache.get(cache_key)
        if isinstance(hit, dict) and hit.get("sha256"):
            return hit

    sha256 = sha256_file(path)
    record = {
        "sha256": sha256,
        "autov2": sha256[:10],
        "autov3": autov3_from_header(path),
    }
    with _lock:
        cache = _load_cache()
        stale = [k for k in cache if k.startswith(key_path + "|")]
        for old in stale:
            cache.pop(old, None)
        cache[cache_key] = record
        _save_cache()
    return record
