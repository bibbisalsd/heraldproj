from __future__ import annotations


def paginate(items: list, page: int = 1, page_size: int = 10) -> dict:
    if page < 1:
        page = 1
    if page_size < 1:
        page_size = 10
    start = (page - 1) * page_size
    end = start + page_size
    return {
        "page": page,
        "page_size": page_size,
        "items": items[start:end],
        "total": len(items),
    }
