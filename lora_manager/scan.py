import os
import threading
import time

from lora_manager.civitai import page_url
from lora_manager.constants import MODEL_EXTS, PREVIEW_EXTS, WALK_MAX_DEPTH
from lora_manager.hashing import cached_hashes, hashes_for
from lora_manager.metadata import load_record
from lora_manager.paths import lora_roots

_CACHE_TTL = 60.0
_cache_lock = threading.Lock()
_cache_items: list[dict] | None = None
_cache_by_key: dict[str, dict] = {}
_cache_at = 0.0


def _inode(path: str) -> tuple:
    try:
        st = os.stat(path, follow_symlinks=True)
        return (getattr(st, "st_dev", 0), getattr(st, "st_ino", 0))
    except OSError:
        return (0, hash(os.path.realpath(path)) & 0xFFFFFFFF)


def find_preview(stem_path: str) -> str | None:
    for suffix in ("", ".preview"):
        for ext in PREVIEW_EXTS:
            candidate = stem_path + suffix + ext
            if os.path.isfile(candidate):
                return ext.lstrip(".")
    folder, stem = os.path.dirname(stem_path), os.path.basename(stem_path)
    try:
        names = os.listdir(folder)
    except OSError:
        return None
    wanted = {stem.lower() + suffix + ext for suffix in ("", ".preview") for ext in PREVIEW_EXTS}
    for name in names:
        if name.lower() in wanted:
            return os.path.splitext(name)[1].lstrip(".").lower()
    return None


def _civitai_ids(meta: dict) -> tuple:
    synced = meta.get("synced") if isinstance(meta.get("synced"), dict) else {}
    civ = meta.get("civitai") if isinstance(meta.get("civitai"), dict) else {}
    model = civ.get("model") if isinstance(civ.get("model"), dict) else {}
    forge = meta.get("forge") if isinstance(meta.get("forge"), dict) else {}
    forge_sync = forge.get("lora_manager_synced") if isinstance(forge.get("lora_manager_synced"), dict) else {}
    model_id = (
        synced.get("modelId")
        or synced.get("model_id")
        or forge_sync.get("modelId")
        or civ.get("modelId")
        or civ.get("model_id")
        or model.get("id")
        or model.get("modelId")
    )
    version_id = (
        synced.get("versionId")
        or synced.get("version_id")
        or forge_sync.get("versionId")
        or civ.get("modelVersionId")
        or civ.get("model_version_id")
        or civ.get("id")
    )
    return model_id, version_id


def sidecar_flags(stem_path: str, model_ext: str) -> dict:
    ext = model_ext.lstrip(".").lower()
    forge = os.path.isfile(stem_path + ".json")
    if not forge:
        forge = os.path.isfile(stem_path + f"_{ext}.json") or os.path.isfile(stem_path + f"-{ext}.json")
    return {
        "has_forge_json": forge,
        "has_comfy_metadata": os.path.isfile(stem_path + ".metadata.json"),
        "has_civitai_info": os.path.isfile(stem_path + ".civitai.info"),
        "has_txt": os.path.isfile(stem_path + ".txt"),
    }


def _rel_posix(root: str, path: str) -> str:
    rel = os.path.relpath(path, root)
    if rel == ".":
        return ""
    return rel.replace("\\", "/")


def scan_loras(*, compute_hashes: bool = True) -> list[dict]:
    items = []
    seen_files = set()
    roots = lora_roots()
    prefix_roots = len(roots) > 1

    for root in roots:
        tag = os.path.basename(root) or os.path.basename(os.path.dirname(root))
        root_depth = root.count(os.sep)
        dir_seen = set()
        for current, dirs, files in os.walk(root, followlinks=True):
            node = _inode(current)
            if node in dir_seen:
                dirs[:] = []
                continue
            dir_seen.add(node)
            if current.count(os.sep) - root_depth > WALK_MAX_DEPTH:
                dirs[:] = []
                continue

            folder_rel = _rel_posix(root, current)
            folder_key = f"[{tag}]/{folder_rel}" if prefix_roots and folder_rel else (
                f"[{tag}]" if prefix_roots else folder_rel
            )

            for filename in files:
                lower = filename.lower()
                if not any(lower.endswith(ext) for ext in MODEL_EXTS):
                    continue
                full = os.path.join(current, filename)
                try:
                    real = os.path.normcase(os.path.realpath(full))
                except OSError:
                    continue
                if real in seen_files:
                    continue
                seen_files.add(real)

                stem, ext = os.path.splitext(filename)
                stem_path = os.path.join(current, stem)
                flags = sidecar_flags(stem_path, ext)
                preview = find_preview(stem_path)
                meta = load_record(full)
                model_id, version_id = _civitai_ids(meta)
                item = {
                    "name": stem,
                    "filename": filename,
                    "key": _rel_posix(root, full),
                    "folder": folder_key,
                    "path": full,
                    "size": 0,
                    "preview": preview,
                    "sha256": meta.get("sha256"),
                    "autov2": None,
                    "autov3": None,
                    "triggers": meta.get("triggers") or [],
                    "preferred_weight": meta.get("preferred_weight") or 0,
                    "base_model": meta.get("sd_version") or "",
                    "notes": meta.get("notes") or "",
                    "description": meta.get("description") or "",
                    "tags": meta.get("tags") or [],
                    "favorite": bool(meta.get("favorite")),
                    "model_id": model_id,
                    "version_id": version_id,
                    "civitai_url": page_url(model_id, version_id),
                    **flags,
                }
                try:
                    item["size"] = os.path.getsize(full)
                except OSError:
                    pass
                cached = cached_hashes(full)
                if cached:
                    item.update(cached)
                elif compute_hashes:
                    try:
                        item.update(hashes_for(full))
                    except OSError:
                        pass
                items.append(item)

    items.sort(key=lambda row: (row["folder"].lower(), row["name"].lower()))
    return items


def _norm_key(key: str) -> str:
    return (key or "").replace("\\", "/").lstrip("/")


def invalidate_scan_cache() -> None:
    global _cache_items, _cache_at
    with _cache_lock:
        _cache_items = None
        _cache_by_key.clear()
        _cache_at = 0.0


def cached_loras(*, compute_hashes: bool = False, force: bool = False) -> list[dict]:
    global _cache_items, _cache_at
    with _cache_lock:
        now = time.monotonic()
        if not force and _cache_items is not None and now - _cache_at < _CACHE_TTL:
            return _cache_items
    items = scan_loras(compute_hashes=False)
    with _cache_lock:
        _cache_items = items
        _cache_by_key.clear()
        _cache_by_key.update((row["key"], row) for row in items)
        _cache_at = time.monotonic()
    return items


def refresh_cached_item(key: str) -> dict | None:
    key = _norm_key(key)
    with _cache_lock:
        row = _cache_by_key.get(key)
        if not row:
            return None
        path = row["path"]
    stem_path, ext = os.path.splitext(path)
    meta = load_record(path)
    flags = sidecar_flags(stem_path, ext)
    preview = find_preview(stem_path)
    cached = cached_hashes(path) or {}
    with _cache_lock:
        cur = _cache_by_key.get(key)
        if not cur:
            return None
        cur["triggers"] = meta.get("triggers") or []
        cur["preferred_weight"] = meta.get("preferred_weight") or 0
        cur["base_model"] = meta.get("sd_version") or ""
        cur["notes"] = meta.get("notes") or ""
        cur["description"] = meta.get("description") or ""
        cur["tags"] = meta.get("tags") or []
        cur["favorite"] = bool(meta.get("favorite"))
        cur["model_id"], cur["version_id"] = _civitai_ids(meta)
        cur["civitai_url"] = page_url(cur["model_id"], cur["version_id"])
        if meta.get("sha256") and not cur.get("sha256"):
            cur["sha256"] = meta.get("sha256")
        cur["preview"] = preview
        cur.update(flags)
        if cached:
            cur.update(cached)
        return dict(cur)


def find_lora(key: str, *, compute_hashes: bool = False) -> dict | None:
    key = _norm_key(key)
    if not key or ".." in key.split("/"):
        return None
    cached_loras()
    with _cache_lock:
        row = _cache_by_key.get(key)
        found = dict(row) if row else None
    if not found:
        cached_loras(force=True)
        with _cache_lock:
            row = _cache_by_key.get(key)
            found = dict(row) if row else None
    if not found:
        return None
    if compute_hashes and not found.get("sha256"):
        try:
            hashes = hashes_for(found["path"])
        except OSError:
            hashes = {}
        found.update(hashes)
        with _cache_lock:
            cur = _cache_by_key.get(key)
            if cur:
                cur.update(hashes)
    return found
