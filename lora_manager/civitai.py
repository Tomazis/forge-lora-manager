from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from typing import Any


SITE_URL = "https://civitai.red"
BASE_URL = f"{SITE_URL}/api/v1"
USER_AGENT = "forge-lora-manager/0.1"


def page_url(model_id: Any = None, version_id: Any = None) -> str:
    """Same shape ComfyUI uses: /models/{id}?modelVersionId={version}."""
    if model_id in (None, "", 0, "0"):
        return SITE_URL
    url = f"{SITE_URL}/models/{model_id}"
    if version_id not in (None, "", 0, "0"):
        url += f"?modelVersionId={version_id}"
    return url


class CivitaiError(Exception):
    def __init__(self, status: str, message: str, http_code: int | None = None):
        super().__init__(message)
        self.status = status
        self.message = message
        self.http_code = http_code


def _headers() -> dict[str, str]:
    headers = {"Accept": "application/json", "User-Agent": USER_AGENT}
    try:
        from lora_manager.settings import api_key

        key = api_key()
    except Exception:
        key = ""
    if key:
        headers["Authorization"] = f"Bearer {key}"
    return headers


def _get(url: str, timeout: int = 30) -> Any:
    req = urllib.request.Request(url, headers=_headers(), method="GET")
    retries = 3
    for attempt in range(retries):
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                raw = resp.read()
            return json.loads(raw.decode("utf-8"))
        except urllib.error.HTTPError as exc:
            if exc.code == 404:
                raise CivitaiError("not_found", "No Civitai match for this hash", 404) from exc
            if exc.code == 429:
                wait = 2 ** attempt
                retry_after = exc.headers.get("Retry-After") if exc.headers else None
                try:
                    wait = max(wait, int(retry_after))
                except (TypeError, ValueError):
                    pass
                if attempt < retries - 1:
                    time.sleep(wait)
                    continue
                raise CivitaiError("rate_limit", "civitai.red rate limited the request", 429) from exc
            if exc.code >= 500 and attempt < retries - 1:
                time.sleep(2 ** attempt)
                continue
            raise CivitaiError("http", f"civitai.red HTTP {exc.code}", exc.code) from exc
        except urllib.error.URLError as exc:
            if attempt < retries - 1:
                time.sleep(2 ** attempt)
                continue
            raise CivitaiError("network", str(exc.reason or exc), None) from exc
        except json.JSONDecodeError as exc:
            raise CivitaiError("invalid", "civitai.red returned non-JSON", None) from exc
    raise CivitaiError("network", "request failed", None)


def version_by_hash(file_hash: str) -> dict:
    file_hash = (file_hash or "").strip()
    if not file_hash:
        raise CivitaiError("invalid", "empty hash")
    return _get(f"{BASE_URL}/model-versions/by-hash/{file_hash}")


def version_by_id(version_id: int) -> dict:
    return _get(f"{BASE_URL}/model-versions/{int(version_id)}")


def model_by_id(model_id: int) -> dict:
    return _get(f"{BASE_URL}/models/{int(model_id)}")


def lookup_hashes(sha256: str | None, autov2: str | None, autov3: str | None) -> dict:
    errors: list[str] = []
    for candidate in (sha256, autov3, autov2):
        if not candidate:
            continue
        try:
            return version_by_hash(candidate)
        except CivitaiError as exc:
            if exc.status == "not_found":
                errors.append(candidate)
                continue
            raise
    raise CivitaiError("not_found", "No Civitai match for SHA256/AutoV2/AutoV3")
