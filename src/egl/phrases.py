from __future__ import annotations

import re

_NON_WORD = re.compile(r"[^0-9a-zа-яё]+", re.IGNORECASE)


def normalize_phrase(value: str) -> str:
    value = value.lower().replace("ё", "е")
    value = _NON_WORD.sub(" ", value)
    return " ".join(value.split())


def phrase_matches(text: str, aliases: list[str]) -> bool:
    normalized = normalize_phrase(text)
    return any(normalized.endswith(normalize_phrase(alias)) for alias in aliases)
