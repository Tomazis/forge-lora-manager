import os
import sys

_EXT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _EXT_ROOT not in sys.path:
    sys.path.insert(0, _EXT_ROOT)

import gradio as gr
from fastapi import FastAPI

from modules import script_callbacks

from lora_manager.api import register_routes
from lora_manager.settings import register_options
from lora_manager.ui import build_tab


def on_ui_settings():
    register_options()


def on_app_started(_blocks: gr.Blocks, app: FastAPI):
    register_routes(app)


def on_ui_tabs():
    return build_tab()


script_callbacks.on_ui_settings(on_ui_settings)
script_callbacks.on_app_started(on_app_started)
script_callbacks.on_ui_tabs(on_ui_tabs)
