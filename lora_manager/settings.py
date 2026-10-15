import os

import gradio as gr

from modules import shared

SECTION = ("lora_manager", "LoRA Manager")

OPT_API_KEY = "lora_manager_civitai_api_key"
OPT_EXAMPLES_DIR = "lora_manager_example_images_dir"
OPT_NSFW_BLUR = "lora_manager_nsfw_blur"

NSFW_CHOICES = ("off", "PG13", "R", "X", "XXX")


def register_options():
    shared.opts.add_option(
        OPT_API_KEY,
        shared.OptionInfo(
            "",
            "Civitai.red API key",
            gr.Textbox,
            {"type": "password", "placeholder": "optional; higher rate limits"},
            section=SECTION,
        ).info("Bearer token from civitai.com; API host is civitai.red"),
    )
    shared.opts.add_option(
        OPT_EXAMPLES_DIR,
        shared.OptionInfo(
            "",
            "Example images directory",
            section=SECTION,
        ).info("empty = <extension>/example_images; one folder per model hash"),
    )
    shared.opts.add_option(
        OPT_NSFW_BLUR,
        shared.OptionInfo(
            "R",
            "Blur previews at or above NSFW level",
            gr.Dropdown,
            {"choices": list(NSFW_CHOICES)},
            section=SECTION,
        ).info("off disables blur"),
    )


def api_key() -> str:
    return (getattr(shared.opts, OPT_API_KEY, None) or "").strip()


def example_images_dir() -> str:
    raw = (getattr(shared.opts, OPT_EXAMPLES_DIR, None) or "").strip()
    if raw:
        return os.path.abspath(os.path.expanduser(raw))
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(root, "example_images")


def nsfw_blur() -> str:
    value = getattr(shared.opts, OPT_NSFW_BLUR, "R") or "off"
    return value if value in NSFW_CHOICES else "R"
