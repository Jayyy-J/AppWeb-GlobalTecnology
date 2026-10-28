import re
import unicodedata


def strip_accents(value: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", value) if unicodedata.category(c) != "Mn")


def normalize(value: str, keep_length: bool = False) -> str:
    """Minúsculas y sin tildes. Con keep_length conserva la longitud (para resaltar)."""
    value = str(value or "")
    if keep_length:
        return "".join(strip_accents(c) or c for c in value).lower()
    value = strip_accents(value).lower()
    value = re.sub(r"[^\w\s\-\.]", " ", value)
    return re.sub(r"\s+", " ", value).strip()
