def normalize_text(value: str) -> str:
    return " ".join(value.casefold().split())
