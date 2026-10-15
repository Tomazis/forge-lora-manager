from __future__ import annotations

import json
import os
import shutil
import urllib.error
import urllib.parse
import urllib.request

from lora_manager.civitai import USER_AGENT
from lora_manager.constants import PREVIEW_EXTS
from lora_manager.scan import find_preview

BLOCKED_PATHS = ("/api/download/models", ".safetensors", ".ckpt", ".pt", ".bin", ".gguf")
IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".webm", ".mp4"}


def _headers() -> dict[str, str]:
    headers = {
        "User-Agent": USER_AGENT,
        "Accept": "image/avif,image/webp,image/apng,image/*,*/*;q=0.8",
        "Referer": "https://civitai.red/",
    }
    try:
        from lora_manager.settings import api_key

        key = api_key()
    except Exception:
        key = ""
    if key:
        headers["Authorization"] = f"Bearer {key}"
    return headers


def _ext_from(url: str, content_type: str) -> str:
    ctype = (content_type or "").split(";")[0].strip().lower()
    mapping = {
        "image/jpeg": ".jpg",
        "image/png": ".png",
        "image/webp": ".webp",
        "image/gif": ".gif",
        "video/mp4": ".mp4",
        "video/webm": ".webm",
    }
    if ctype in mapping:
        return mapping[ctype]
    path = urllib.parse.urlparse(url).path.lower()
    for ext in IMAGE_EXTS:
        if path.endswith(ext):
            return ext
    return ".jpg"


def is_weight_url(url: str) -> bool:
    lower = (url or "").lower()
    return any(part in lower for part in BLOCKED_PATHS)


def download_bytes(url: str, dest: str, timeout: int = 60) -> str | None:
    if not url or is_weight_url(url):
        return None
    req = urllib.request.Request(url, headers=_headers(), method="GET")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            ctype = resp.headers.get("Content-Type", "")
            if "octet-stream" in ctype and is_weight_url(url):
                return None
            data = resp.read()
            ext = _ext_from(url, ctype)
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, OSError):
        return None
    if len(data) < 32:
        return None
    os.makedirs(os.path.dirname(dest) or ".", exist_ok=True)
    final = dest if dest.lower().endswith(tuple(IMAGE_EXTS)) else dest + ext
    tmp = final + ".tmp"
    with open(tmp, "wb") as fh:
        fh.write(data)
    os.replace(tmp, final)
    return final


def examples_dir_for(sha256: str) -> str:
    digest = (sha256 or "unknown").lower()
    try:
        from lora_manager.settings import example_images_dir

        root = example_images_dir()
    except Exception:
        root = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "example_images")
    return os.path.join(root, digest)


def _image_url(entry: dict) -> str:
    if not isinstance(entry, dict):
        return ""
    return (
        entry.get("url")
        or (entry.get("availableSizes") or [{}])[-1].get("url")
        or ""
    )


def _image_urls(entry: dict) -> list[str]:
    url = _image_url(entry)
    if not url:
        return []
    out: list[str] = []
    variants = [url]
    if "image.civitai.com" in url:
        variants.append(url.replace("image.civitai.com", "image.civitai.red"))
    if "://civitai.com/" in url and "civitai.red" not in url:
        variants.append(url.replace("://civitai.com/", "://civitai.red/"))
    for item in variants:
        if item not in out:
            out.append(item)
        if "/original=true/" in item:
            alt = item.replace("/original=true/", "/width=768/")
            if alt not in out:
                out.append(alt)
    return out


def _existing_example(dest: str) -> str | None:
    if dest.lower().endswith(tuple(IMAGE_EXTS)) and os.path.isfile(dest):
        return dest
    for ext in (".jpeg", ".jpg", ".png", ".webp", ".gif", ".webm", ".mp4"):
        cand = dest + ext
        if os.path.isfile(cand):
            return cand
    return None


def ensure_preview(model_path: str, images: list) -> str | None:
    stem, _ = os.path.splitext(model_path)
    if find_preview(stem):
        existing = None
        for suffix in ("", ".preview"):
            for ext in PREVIEW_EXTS:
                cand = stem + suffix + ext
                if os.path.isfile(cand):
                    existing = cand
                    break
            if existing:
                break
        return existing
    for entry in images or []:
        if (entry.get("type") or "image") == "video":
            continue
        dest = stem + ".preview"
        existing = _existing_example(dest)
        if existing:
            return existing
        for url in _image_urls(entry):
            saved = download_bytes(url, dest)
            if saved:
                return saved
    return None


def ensure_examples(sha256: str, images: list) -> list[dict]:
    folder = examples_dir_for(sha256)
    os.makedirs(folder, exist_ok=True)
    index_path = os.path.join(folder, "index.json")
    saved = []
    for i, entry in enumerate(images or []):
        kind = entry.get("type") or "image"
        dest = os.path.join(folder, f"{i:03d}")
        path = _existing_example(dest)
        if not path:
            for url in _image_urls(entry):
                path = download_bytes(url, dest)
                if path:
                    break
        if path:
            saved.append(
                {
                    "index": i,
                    "file": os.path.basename(path),
                    "nsfwLevel": entry.get("nsfwLevel") or 0,
                    "type": kind,
                    "meta": entry.get("meta"),
                    "width": entry.get("width"),
                    "height": entry.get("height"),
                }
            )
    if not saved:
        saved = _examples_from_folder(folder)
    if saved:
        with open(index_path, "w", encoding="utf-8") as fh:
            json.dump(saved, fh, ensure_ascii=False, indent=2)
    return saved


def _examples_from_folder(folder: str) -> list[dict]:
    if not os.path.isdir(folder):
        return []
    try:
        names = sorted(os.listdir(folder))
    except OSError:
        return []
    items = []
    index = 0
    for name in names:
        ext = os.path.splitext(name)[1].lower()
        if ext not in IMAGE_EXTS:
            continue
        items.append(
            {
                "index": index,
                "file": name,
                "nsfwLevel": 0,
                "type": "video" if ext in {".webm", ".mp4"} else "image",
                "meta": {},
            }
        )
        index += 1
    return items


def list_examples(sha256: str) -> list[dict]:
    folder = examples_dir_for(sha256)
    index_path = os.path.join(folder, "index.json")
    if os.path.isfile(index_path):
        try:
            with open(index_path, encoding="utf-8") as fh:
                data = json.load(fh)
            if isinstance(data, list) and data:
                return data
        except (OSError, json.JSONDecodeError):
            pass
    if not sha256:
        return []
    return _examples_from_folder(folder)


def set_preview_from_example(model_path: str, sha256: str, index: int) -> bool:
    examples = list_examples(sha256)
    match = next((e for e in examples if e.get("index") == index), None)
    if not match or not match.get("file"):
        return False
    src = os.path.join(examples_dir_for(sha256), match["file"])
    if not os.path.isfile(src):
        return False
    stem, _ = os.path.splitext(model_path)
    ext = os.path.splitext(src)[1]
    dest = stem + ".preview" + ext
    shutil.copy2(src, dest)
    return True
