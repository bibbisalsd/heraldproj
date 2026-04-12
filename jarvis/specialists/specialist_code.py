from __future__ import annotations

from jarvis.models.code import analyze as analyze_code


def run(task: str, model: str | None = None, reviewer_model: str | None = None) -> dict:
    result = analyze_code(task, model=model, reviewer_model=reviewer_model)
    if result.get("ok"):
        summary = str(result.get("summary", "")).strip()
        snippet = summary[:350] if summary else "done"
        return {
            "ok": True,
            "task": task,
            "result": f"Code specialist result: {snippet}",
            "retryable": False,
            "model": result.get("model"),
            "provenance": "inferred",
        }
    return {
        "ok": True,
        "task": task,
        "result": f"Code specialist fallback: {result.get('summary', 'model unavailable')}",
        "retryable": True,
        "model": result.get("model"),
        "provenance": "inferred",
    }
