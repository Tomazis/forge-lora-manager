import os

from fastapi import FastAPI, Query, Request
from fastapi.responses import FileResponse, JSONResponse

from lora_manager import __version__
from lora_manager.assets import examples_dir_for, list_examples, set_preview_from_example
from lora_manager.constants import PREVIEW_EXTS
from lora_manager.metadata import apply_user_edits, load_record, save_record
from lora_manager.scan import cached_loras, find_lora, refresh_cached_item
from lora_manager.settings import nsfw_blur
from lora_manager.sync import job_status, start_sync_all, sync_one


def _public_item(row: dict) -> dict:
    return {k: v for k, v in row.items() if k != "path"}


async def _json_body(request: Request) -> dict:
    try:
        data = await request.json()
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def register_routes(app: FastAPI):
    @app.get("/lora-manager/version")
    def version():
        return {"ok": True, "name": "forge-lora-manager", "version": __version__}

    @app.get("/lora-manager/list")
    def list_loras(include_hash: bool = Query(False)):
        items = [_public_item(row) for row in cached_loras(compute_hashes=include_hash)]
        return {"ok": True, "count": len(items), "items": items}

    @app.get("/lora-manager/item")
    def item(key: str = Query(...)):
        row = find_lora(key, compute_hashes=False)
        if not row:
            return JSONResponse({"ok": False, "error": "not found"}, status_code=404)
        return {"ok": True, "item": _public_item(row)}

    @app.post("/lora-manager/sync")
    async def sync(request: Request):
        body = await _json_body(request)
        return sync_one(body.get("key") or "")

    @app.post("/lora-manager/sync-all")
    def sync_all(missing_only: bool = Query(False)):
        job_id = start_sync_all(missing_only=missing_only)
        return {"ok": True, "job": job_id}

    @app.get("/lora-manager/sync-progress")
    def sync_progress(job: str = Query(...)):
        data = job_status(job)
        if not data:
            return {"ok": False, "status": "missing", "error": "unknown job"}
        return {"ok": True, **data}

    @app.post("/lora-manager/save")
    async def save(request: Request):
        body = await _json_body(request)
        key = body.get("key") or ""
        row = find_lora(key, compute_hashes=False)
        if not row:
            return {"ok": False, "status": "missing", "error": "LoRA not found"}
        record = apply_user_edits(
            load_record(row["path"]),
            triggers=body.get("triggers"),
            notes=body.get("notes"),
            preferred_weight=body.get("preferred_weight"),
            description=body.get("description"),
            sd_version=body.get("sd_version"),
            negative_text=body.get("negative_text"),
            favorite=body.get("favorite"),
        )
        save_record(record)
        refresh_cached_item(key)
        return {"ok": True, "key": key, "triggers": record.get("triggers") or []}

    @app.get("/lora-manager/preview")
    def preview(key: str = Query(...)):
        row = find_lora(key, compute_hashes=False)
        if not row:
            return JSONResponse({"ok": False, "error": "not found"}, status_code=404)
        stem, _ = os.path.splitext(row["path"])
        for suffix in ("", ".preview"):
            for ext in PREVIEW_EXTS:
                path = stem + suffix + ext
                if os.path.isfile(path):
                    return FileResponse(path, headers={"Cache-Control": "public, max-age=86400"})
        return JSONResponse({"ok": False, "error": "no preview"}, status_code=404)

    @app.get("/lora-manager/examples")
    def examples(key: str = Query(...)):
        row = find_lora(key, compute_hashes=True)
        if not row:
            print(f"[lora-manager] examples miss key={key!r}", flush=True)
            return {"ok": False, "error": "not found", "items": []}
        sha = row.get("sha256")
        folder = examples_dir_for(sha)
        items = list_examples(sha)
        print(
            f"[lora-manager] examples key={key!r} sha={sha!r} dir={folder!r} "
            f"dir_exists={os.path.isdir(folder)} index={os.path.isfile(os.path.join(folder, 'index.json'))} "
            f"count={len(items)}",
            flush=True,
        )
        return {
            "ok": True,
            "sha256": sha,
            "dir": folder,
            "dir_exists": os.path.isdir(folder),
            "has_index": os.path.isfile(os.path.join(folder, "index.json")),
            "nsfw_blur": nsfw_blur(),
            "items": [
                {
                    **item,
                    "url": f"/lora-manager/example-file?key={key}&index={item.get('index')}",
                }
                for item in items
            ],
        }

    @app.get("/lora-manager/example-file")
    def example_file(key: str = Query(...), index: int = Query(...)):
        row = find_lora(key, compute_hashes=True)
        if not row:
            return JSONResponse({"ok": False}, status_code=404)
        sha = row.get("sha256")
        match = next((e for e in list_examples(sha) if e.get("index") == index), None)
        if not match or not match.get("file"):
            return JSONResponse({"ok": False}, status_code=404)
        path = os.path.join(examples_dir_for(sha), match["file"])
        if not os.path.isfile(path):
            return JSONResponse({"ok": False}, status_code=404)
        return FileResponse(path, headers={"Cache-Control": "public, max-age=86400"})

    @app.post("/lora-manager/set-preview")
    async def set_preview(request: Request):
        body = await _json_body(request)
        key = body.get("key") or ""
        index = int(body.get("index") or 0)
        row = find_lora(key, compute_hashes=True)
        if not row:
            return {"ok": False, "error": "not found"}
        sha = row.get("sha256")
        ok = set_preview_from_example(row["path"], sha, index)
        if ok:
            refresh_cached_item(key)
        return {"ok": ok}
