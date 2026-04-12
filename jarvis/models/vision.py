from __future__ import annotations

import os

from .ollama_client import OllamaClient
from .workspace_inputs import collect_image_inputs


def analyze(image_ref: str, model: str | None = None) -> dict:
    model_id = model or os.getenv("JARVIS_VISION_LITE_MODEL", "qwen2.5vl:3b")
    client = OllamaClient(model=model_id)
    images = collect_image_inputs(image_ref)
    prompt = _build_prompt(image_ref, images)

    if images:
        result = client.run(
            prompt,
            images=[item["base64"] for item in images],
        )
    else:
        result = client.run(prompt)

    if result.ok:
        return {
            "ok": True,
            "image_ref": image_ref,
            "model": model_id,
            "summary": result.text or "no_output",
            "image_count": len(images),
        }
    return {
        "ok": False,
        "image_ref": image_ref,
        "model": model_id,
        "summary": result.error,
    }


def _build_prompt(image_ref: str, images: list[dict[str, str]]) -> str:
    sections = [
        "You are a local vision assistant.",
        "Analyze the user request and return a concise result.",
        f"Request: {image_ref}",
    ]
    if images:
        listed = "\n".join(f"- {item['path']}" for item in images)
        sections.append("Attached workspace images:\n" + listed)
        sections.append("Use the attached images as the primary source of truth.")
    return "\n\n".join(sections)
