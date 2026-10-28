"""Versionado de fragmentos cacheados (menú de categorías, home)."""
from django.core.cache import cache

KEYS = ("menu", "home")


def get_version(name: str) -> int:
    v = cache.get(f"fragver:{name}")
    if v is None:
        v = 1
        cache.set(f"fragver:{name}", v, None)
    return v


def bump(*names: str):
    for name in names or KEYS:
        try:
            cache.incr(f"fragver:{name}")
        except ValueError:
            cache.set(f"fragver:{name}", 2, None)
