# Forge LoRA Manager

Local LoRA browser for Stable Diffusion WebUI Forge Neo: a QuickPick-style selector under the prompt, plus a **LoRA Manager** tab for the full library.

Metadata is synced from [civitai.red](https://civitai.red) for files that are **already on disk**. This extension does **not** download LoRA weights (`.safetensors` / `.pt` / …).

## Install

1. Place this folder in Forge Neo `extensions/forge-lora-manager` (or Install from URL).
2. Restart WebUI.
3. Settings → **LoRA Manager**: paste a Civitai API key (optional, from civitai.com account settings; used as Bearer against civitai.red).
4. Disable **LoRA QuickPick** if both are installed — they both inject tags on Generate.

## UI

- **txt2img / img2img**: picker under the prompt. Click a LoRA to select it; click the chip name to show or hide trigger words (toggle on/off). Presets live in the picker menu. On Generate, enabled triggers and `<lora:name:weight>` are injected for that request, then the visible prompt is restored.
- **LoRA Manager tab**: library, folder list, filters, card details, sync, examples, notes. Right-click a LoRA in the picker to open the same card in a modal.

Styles and click handling live in `style.css` and `javascript/lora_manager.js` (Forge loads them automatically). After UI changes, restart WebUI or hard-refresh the page.

## Sidecar files (both are written)

Next to `my_lora.safetensors`:

| File | Who reads it |
|------|----------------|
| `my_lora.json` | Forge Extra Networks (`activation text`, `preferred weight`, notes) |
| `my_lora.metadata.json` | ComfyUI LoRA Manager |

Existing `.civitai.info` and `.txt` sidecars are read as extra sources. Manual notes, preferred weight, and custom triggers are not overwritten by a sync when they already differ from the API.

## Not in v1

- Downloading models from Civitai
- Checkpoints, embeddings, recipes
- ComfyUI nodes / browser extension
