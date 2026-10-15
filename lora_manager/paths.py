import os

from lora_manager.constants import CANDIDATE_DIRNAMES


def _split_paths(raw: str) -> list[str]:
    if not raw:
        return []
    seps = [";"]
    if os.name != "nt":
        seps.append(":")
    parts = [raw]
    for sep in seps:
        next_parts = []
        for item in parts:
            next_parts.extend(item.split(sep))
        parts = next_parts
    out = []
    for item in parts:
        cleaned = item.strip().strip('"')
        if cleaned:
            out.append(os.path.abspath(os.path.expanduser(cleaned)))
    return out


def _first_existing(paths: list[str]) -> list[str]:
    for path in paths:
        if os.path.isdir(path):
            return [path]
    return []


def lora_roots() -> list[str]:
    try:
        from modules import shared
    except Exception:
        shared = None

    try:
        ldir = getattr(shared.opts, "lora_dir", None) if shared else None
        if ldir:
            found = _first_existing(_split_paths(ldir))
            if found:
                return found
    except Exception:
        pass

    try:
        args = getattr(shared, "cmd_opts", None)
        if isinstance(args, (list, tuple)):
            for i, arg in enumerate(args):
                if arg == "--lora-dir" and i + 1 < len(args):
                    found = _first_existing(_split_paths(args[i + 1]))
                    if found:
                        return found
        else:
            val = getattr(args, "lora_dir", None)
            if val:
                found = _first_existing(_split_paths(val))
                if found:
                    return found
    except Exception:
        pass

    for key in ("LORA_DIR", "LORAS_DIR"):
        found = _first_existing(_split_paths(os.environ.get(key, "") or ""))
        if found:
            return found

    try:
        base = getattr(shared, "models_path", None) or getattr(shared, "model_path", None)
        if base:
            for name in CANDIDATE_DIRNAMES:
                candidate = os.path.abspath(os.path.join(base, name))
                if os.path.isdir(candidate):
                    return [candidate]
    except Exception:
        pass

    here = os.getcwd()
    for name in CANDIDATE_DIRNAMES:
        candidate = os.path.abspath(os.path.join(here, "models", name))
        if os.path.isdir(candidate):
            return [candidate]

    return []
