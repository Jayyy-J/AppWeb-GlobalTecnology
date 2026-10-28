"""Filtros de formato colombiano. `cop` es builtin (no requiere {% load %})."""
import json

from django import template
from django.utils.html import escape
from django.utils.safestring import mark_safe

register = template.Library()


def format_cop(value) -> str:
    try:
        n = int(round(float(value)))
    except (TypeError, ValueError):
        return ""
    sign = "-" if n < 0 else ""
    return f"{sign}${abs(n):,}".replace(",", ".")


@register.filter(name="cop")
def cop(value):
    """1299900 -> $1.299.900"""
    return format_cop(value)


@register.filter
def resaltar(texto, termino):
    """Resalta (sin tildes ni mayúsculas) el término dentro del texto con <mark>."""
    from apps.core.text import normalize

    texto = str(texto or "")
    termino = (termino or "").strip()
    if not termino:
        return escape(texto)
    norm_texto = normalize(texto, keep_length=True)
    partes, i = [], 0
    palabras = [p for p in normalize(termino).split() if len(p) >= 2]
    spans = []
    for p in palabras:
        start = 0
        while True:
            idx = norm_texto.find(p, start)
            if idx < 0:
                break
            spans.append((idx, idx + len(p)))
            start = idx + len(p)
    spans.sort()
    merged = []
    for s, e in spans:
        if merged and s <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(e, merged[-1][1]))
        else:
            merged.append((s, e))
    for s, e in merged:
        partes.append(escape(texto[i:s]))
        partes.append(f"<mark>{escape(texto[s:e])}</mark>")
        i = e
    partes.append(escape(texto[i:]))
    return mark_safe("".join(partes))


@register.filter
def json_ld(data):
    """Serializa un dict para <script type="application/ld+json"> de forma segura."""
    raw = json.dumps(data, ensure_ascii=False)
    return mark_safe(raw.replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026"))


@register.simple_tag(takes_context=True)
def url_con(context, **kwargs):
    """Devuelve la query string actual reemplazando/eliminando parámetros (valor None o '' elimina)."""
    request = context["request"]
    params = request.GET.copy()
    params.pop("pagina", None)
    for k, v in kwargs.items():
        if v is None or v == "":
            params.pop(k, None)
        else:
            params[k] = v
    qs = params.urlencode()
    return f"?{qs}" if qs else "?"
