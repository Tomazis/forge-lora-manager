import gradio as gr


def build_tab():
    with gr.Blocks(analytics_enabled=False) as tab:
        gr.HTML('<div id="lora-manager-tab-root" class="lora-manager-tab"></div>')
    return [(tab, "LoRA Manager", "lora_manager")]
