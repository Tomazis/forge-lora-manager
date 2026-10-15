from __future__ import annotations

import json
import os
import time
from copy import deepcopy
from typing import Any

FORGE_TRIGGER_KEYS = (
    "activation text",
    "activation_text",
    "activation",
    "trigger",
    "trigger_words",
    "trainedWords",
    "triggerWords",
)


def normalize_words(raw: Any) -> list[str]:
    if raw is None:
        return []
    if isinstance(raw, list):
        parts: list[str] = []
        for item in raw:
            parts.extend(normalize_words(item))
        return _dedupe(parts)
    text = str(raw).strip()
    if not text:
        return []
    text = text.splitlines()[0].strip()
    chunks = text.split(",")
    return _dedupe(p.strip() for p in chunks if p.strip())


def _dedupe(words) -> list[str]:
    out, seen = [], set()
    for word in words:
        key = word.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(word)
    return out


def activation_text(words: list[str]) -> str:
    return ", ".join(words)


def _read_json(path: str) -> dict:
    try:
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
        return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def _write_json(path: str, data: dict):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(data, fh, ensure_ascii=False, indent=2)
        fh.write("\n")
    os.replace(tmp, path)


def sidecar_paths(model_path: str) -> dict[str, str]:
    stem, ext = os.path.splitext(model_path)
    ext_l = ext.lstrip(".").lower()
    return {
        "forge": stem + ".json",
        "forge_alt_underscore": stem + f"_{ext_l}.json",
        "forge_alt_dash": stem + f"-{ext_l}.json",
        "comfy": stem + ".metadata.json",
        "civitai_info": stem + ".civitai.info",
        "txt": stem + ".txt",
    }


def _preferred_weight(data: dict) -> float:
    raw = data.get("preferred weight", data.get("preferred_weight", 0))
    try:
        return float(raw or 0)
    except (TypeError, ValueError):
        return 0.0


def _triggers_from_mapping(data: dict) -> list[str]:
    for key in FORGE_TRIGGER_KEYS:
        if key in data:
            words = normalize_words(data.get(key))
            if words:
                return words
    civitai = data.get("civitai")
    if isinstance(civitai, dict):
        words = normalize_words(civitai.get("trainedWords") or civitai.get("triggerWords"))
        if words:
            return words
    return []


def load_record(model_path: str) -> dict:
    paths = sidecar_paths(model_path)
    forge_path = paths["forge"]
    for alt in (paths["forge_alt_underscore"], paths["forge_alt_dash"]):
        if not os.path.isfile(forge_path) and os.path.isfile(alt):
            forge_path = alt
            break

    forge = _read_json(forge_path) if os.path.isfile(forge_path) else {}
    comfy = _read_json(paths["comfy"]) if os.path.isfile(paths["comfy"]) else {}
    civinfo = _read_json(paths["civitai_info"]) if os.path.isfile(paths["civitai_info"]) else {}

    triggers = (
        _triggers_from_mapping(forge)
        or _triggers_from_mapping(comfy)
        or _triggers_from_mapping(civinfo)
    )
    if not triggers and os.path.isfile(paths["txt"]):
        try:
            with open(paths["txt"], encoding="utf-8", errors="ignore") as fh:
                triggers = normalize_words(fh.read())
        except OSError:
            pass

    notes = str(forge.get("notes") or comfy.get("notes") or "")
    description = str(
        forge.get("description")
        or comfy.get("modelDescription")
        or (comfy.get("civitai") or {}).get("model", {}).get("description")
        or ""
    )
    weight = _preferred_weight(forge)
    if not weight:
        tips = comfy.get("usage_tips")
        if isinstance(tips, str):
            try:
                tips = json.loads(tips)
            except json.JSONDecodeError:
                tips = {}
        if isinstance(tips, dict):
            try:
                weight = float(tips.get("strength") or 0)
            except (TypeError, ValueError):
                weight = 0.0

    civitai = {}
    if isinstance(comfy.get("civitai"), dict):
        civitai = deepcopy(comfy["civitai"])
    elif civinfo:
        civitai = deepcopy(civinfo)

    synced = comfy.get("lora_manager_synced") if isinstance(comfy.get("lora_manager_synced"), dict) else {}
    if not synced and isinstance(forge.get("lora_manager_synced"), dict):
        synced = forge["lora_manager_synced"]

    sha = str(comfy.get("sha256") or "").strip().lower()
    if not sha:
        files = civitai.get("files") if isinstance(civitai.get("files"), list) else []
        file0 = files[0] if files and isinstance(files[0], dict) else {}
        hashes = file0.get("hashes") if isinstance(file0.get("hashes"), dict) else {}
        sha = str(hashes.get("SHA256") or hashes.get("AutoV2") or "").strip().lower()

    return {
        "model_path": model_path,
        "forge_path": forge_path,
        "comfy_path": paths["comfy"],
        "forge": forge,
        "comfy": comfy,
        "triggers": triggers,
        "notes": notes,
        "description": description,
        "preferred_weight": weight,
        "sd_version": str(forge.get("sd version") or comfy.get("base_model") or ""),
        "negative_text": str(forge.get("negative text") or ""),
        "tags": list(comfy.get("tags") or []),
        "civitai": civitai,
        "favorite": bool(comfy.get("favorite") or forge.get("favorite")),
        "synced": dict(synced),
        "preview_url": comfy.get("preview_url") or "",
        "sha256": sha or None,
    }


def merge_api(record: dict, api: dict, *, file_stat: dict | None = None) -> dict:
    """Merge Civitai version payload into a loaded record without clobbering user fields."""
    out = deepcopy(record)
    api = api or {}
    trained = normalize_words(api.get("trainedWords") or api.get("triggerWords"))
    last_api = normalize_words(out["synced"].get("trainedWords"))
    current = normalize_words(out.get("triggers"))

    if not current:
        triggers = trained
    elif last_api:
        triggers = current if current != last_api else (trained or current)
    else:
        triggers = current if current != trained else (trained or current)

    api_weight = 0.0
    # Civitai does not always send preferred weight; keep user value if set.
    user_weight = float(out.get("preferred_weight") or 0)
    preferred = user_weight if user_weight else api_weight

    notes = out.get("notes") or ""
    description = out.get("description") or ""
    model = api.get("model") if isinstance(api.get("model"), dict) else {}
    api_desc = str(model.get("description") or api.get("description") or "")
    if not description:
        description = api_desc

    tags = list(out.get("tags") or [])
    api_tags = model.get("tags") if isinstance(model.get("tags"), list) else api.get("tags")
    if isinstance(api_tags, list):
        tags = _dedupe([*tags, *[str(t) for t in api_tags if t]])

    base = str(api.get("baseModel") or out.get("sd_version") or "")
    civitai = deepcopy(out.get("civitai") or {})
    civitai.update(api)
    if trained:
        civitai["trainedWords"] = trained

    synced = dict(out.get("synced") or {})
    synced["trainedWords"] = trained
    synced["checked_at"] = time.time()
    synced["modelId"] = api.get("modelId") or (model.get("id") if model else None)
    synced["versionId"] = api.get("id")

    images = api.get("images") if isinstance(api.get("images"), list) else []

    out.update(
        {
            "triggers": triggers,
            "preferred_weight": preferred,
            "notes": notes,
            "description": description,
            "sd_version": base or out.get("sd_version") or "",
            "tags": tags,
            "civitai": civitai,
            "synced": synced,
            "example_images": images,
        }
    )
    if file_stat:
        out["file_stat"] = file_stat
    return out


def apply_user_edits(record: dict, *, triggers=None, notes=None, preferred_weight=None, description=None, sd_version=None, negative_text=None, favorite=None) -> dict:
    out = deepcopy(record)
    if triggers is not None:
        words = normalize_words(triggers)
        out["triggers"] = words
        civitai = deepcopy(out.get("civitai") or {})
        civitai["trainedWords"] = words
        out["civitai"] = civitai
    if notes is not None:
        out["notes"] = str(notes)
    if preferred_weight is not None:
        out["preferred_weight"] = float(preferred_weight or 0)
    if description is not None:
        out["description"] = str(description)
    if sd_version is not None:
        out["sd_version"] = str(sd_version)
    if negative_text is not None:
        out["negative_text"] = str(negative_text)
    if favorite is not None:
        out["favorite"] = bool(favorite)
    return out


def forge_payload(record: dict) -> dict:
    data = dict(record.get("forge") or {})
    data["description"] = record.get("description") or data.get("description") or ""
    data["sd version"] = record.get("sd_version") or data.get("sd version") or ""
    data["activation text"] = activation_text(record.get("triggers") or [])
    data["preferred weight"] = float(record.get("preferred_weight") or 0)
    data["negative text"] = record.get("negative_text") or data.get("negative text") or ""
    data["notes"] = record.get("notes") or ""
    if record.get("favorite"):
        data["favorite"] = True
    data["lora_manager_synced"] = record.get("synced") or {}
    return data


def comfy_payload(record: dict) -> dict:
    model_path = record["model_path"]
    stem = os.path.splitext(os.path.basename(model_path))[0]
    existing = dict(record.get("comfy") or {})
    stat = record.get("file_stat") or {}
    size = stat.get("size")
    if size is None:
        try:
            size = os.path.getsize(model_path)
        except OSError:
            size = existing.get("size") or 0

    tips = existing.get("usage_tips") or "{}"
    if isinstance(tips, dict):
        tips_obj = dict(tips)
    else:
        try:
            tips_obj = json.loads(tips) if tips else {}
        except json.JSONDecodeError:
            tips_obj = {}
    if record.get("preferred_weight"):
        tips_obj["strength"] = float(record["preferred_weight"])

    civitai = deepcopy(record.get("civitai") or {})
    if record.get("triggers"):
        civitai["trainedWords"] = list(record["triggers"])

    existing.update(
        {
            "file_name": stem,
            "model_name": existing.get("model_name") or civitai.get("model", {}).get("name") or stem,
            "file_path": model_path.replace("\\", "/"),
            "size": size,
            "modified": existing.get("modified") or time.time(),
            "sha256": (record.get("sha256") or existing.get("sha256") or "").lower(),
            "base_model": record.get("sd_version") or existing.get("base_model") or "",
            "preview_url": record.get("preview_url") or existing.get("preview_url") or "",
            "notes": record.get("notes") or "",
            "from_civitai": bool(civitai.get("id") or existing.get("from_civitai", True)),
            "civitai": civitai,
            "tags": record.get("tags") or existing.get("tags") or [],
            "modelDescription": record.get("description") or existing.get("modelDescription") or "",
            "favorite": bool(record.get("favorite")),
            "usage_tips": json.dumps(tips_obj, ensure_ascii=False),
            "metadata_source": "civitai.red" if civitai.get("id") else existing.get("metadata_source"),
            "last_checked_at": (record.get("synced") or {}).get("checked_at") or existing.get("last_checked_at") or 0,
            "lora_manager_synced": record.get("synced") or {},
        }
    )
    if record.get("autov3") is not None:
        existing["autov3"] = record["autov3"]
    return existing


def save_record(record: dict):
    paths = sidecar_paths(record["model_path"])
    _write_json(paths["forge"], forge_payload(record))
    _write_json(paths["comfy"], comfy_payload(record))
