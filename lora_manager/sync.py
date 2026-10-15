from __future__ import annotations

import threading
import time
import uuid

from lora_manager.assets import ensure_examples, ensure_preview
from lora_manager.civitai import CivitaiError, lookup_hashes, model_by_id
from lora_manager.hashing import hashes_for
from lora_manager.metadata import load_record, merge_api, save_record
from lora_manager.scan import cached_loras, find_lora, invalidate_scan_cache, refresh_cached_item

_jobs: dict[str, dict] = {}
_jobs_lock = threading.Lock()


def _enrich_version(version: dict) -> dict:
    model = version.get("model") if isinstance(version.get("model"), dict) else {}
    model_id = version.get("modelId") or model.get("id")
    if model_id and not model.get("description"):
        try:
            full = model_by_id(int(model_id))
            merged = dict(model)
            merged.update({k: full.get(k) for k in ("name", "type", "description", "tags", "nsfw", "creator") if k in full})
            if isinstance(full.get("creator"), dict):
                merged["creator"] = full["creator"]
            version = dict(version)
            version["model"] = merged
            version["modelId"] = model_id
        except CivitaiError:
            pass
    return version


def sync_one(key: str) -> dict:
    row = find_lora(key, compute_hashes=False)
    if not row:
        return {"ok": False, "key": key, "status": "missing", "error": "LoRA not found"}
    path = row["path"]
    try:
        hashes = hashes_for(path)
    except OSError as exc:
        return {"ok": False, "key": key, "status": "hash_failed", "error": str(exc)}

    try:
        version = lookup_hashes(hashes.get("sha256"), hashes.get("autov2"), hashes.get("autov3"))
        version = _enrich_version(version)
    except CivitaiError as exc:
        record = load_record(path)
        sidecars = (record.get("civitai") or {}).get("images") if isinstance(record.get("civitai"), dict) else []
        sha = hashes.get("sha256") or record.get("sha256")
        examples = ensure_examples(sha, sidecars) if sha and sidecars else []
        return {
            "ok": False,
            "key": key,
            "name": row["name"],
            "status": exc.status,
            "error": exc.message,
            "sha256": sha,
            "examples": len(examples),
        }

    record = load_record(path)
    sidecar_images = (record.get("civitai") or {}).get("images") if isinstance(record.get("civitai"), dict) else []
    record["sha256"] = hashes.get("sha256") or record.get("sha256")
    record["autov3"] = hashes.get("autov3")
    record = merge_api(record, version, file_stat={"size": row.get("size")})
    images = record.get("example_images") or version.get("images") or sidecar_images or []
    preview = ensure_preview(path, images)
    if preview:
        record["preview_url"] = preview.replace("\\", "/")
    examples = []
    sha = hashes.get("sha256") or record.get("sha256")
    if sha:
        examples = ensure_examples(sha, images)
    save_record(record)
    refresh_cached_item(key)
    return {
        "ok": True,
        "key": key,
        "name": row["name"],
        "status": "synced",
        "triggers": record.get("triggers") or [],
        "base_model": record.get("sd_version") or "",
        "model_id": (record.get("synced") or {}).get("modelId"),
        "version_id": (record.get("synced") or {}).get("versionId"),
        "examples": len(examples),
        "preview": bool(preview),
    }


def start_sync_all(*, missing_only: bool = False) -> str:
    job_id = uuid.uuid4().hex[:12]
    rows = cached_loras(compute_hashes=False, force=True)
    if missing_only:
        rows = [r for r in rows if not r.get("has_comfy_metadata") and not r.get("has_forge_json")]
    job = {
        "id": job_id,
        "total": len(rows),
        "done": 0,
        "ok": 0,
        "failed": 0,
        "running": True,
        "results": [],
        "started": time.time(),
    }
    with _jobs_lock:
        _jobs[job_id] = job

    def worker():
        for row in rows:
            result = sync_one(row["key"])
            with _jobs_lock:
                job["results"].append(result)
                job["done"] += 1
                if result.get("ok"):
                    job["ok"] += 1
                else:
                    job["failed"] += 1
        invalidate_scan_cache()
        with _jobs_lock:
            job["running"] = False
            job["finished"] = time.time()

    threading.Thread(target=worker, name=f"lora-sync-{job_id}", daemon=True).start()
    return job_id


def job_status(job_id: str) -> dict | None:
    with _jobs_lock:
        job = _jobs.get(job_id)
        return dict(job) if job else None
