from __future__ import annotations


def evaluate(expression: str) -> dict:
    allowed = set("0123456789+-*/(). ")
    if any(ch not in allowed for ch in expression):
        return {"ok": False, "reason": "invalid_expression"}
    try:
        value = eval(expression, {"__builtins__": {}}, {})
    except Exception as exc:
        return {"ok": False, "reason": str(exc)}
    return {"ok": True, "value": value}
