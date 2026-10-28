"""Búsqueda de productos.

PostgreSQL: SearchRank sobre search_vector (nombre A, marca/categorías B,
descripción/especificaciones C) + TrigramWordSimilarity sobre el nombre sin
tildes (unaccent) para tolerar errores de escritura.
SQLite (solo desarrollo): degrada a icontains sobre un texto normalizado.
"""
import difflib
import logging

from django.contrib.postgres.search import SearchQuery, SearchRank, SearchVector, TrigramWordSimilarity
from django.core.cache import cache
from django.db import models
from django.db.models import F, FloatField, Q, Value
from django.db.models.functions import Greatest, Lower
from django.utils import timezone
from django.utils.html import strip_tags

from apps.core.text import normalize

logger = logging.getLogger(__name__)
SIM_UMBRAL = 0.42
CONFIG = "spanish"


class Unaccent(models.Func):
    function = "unaccent"
    output_field = models.TextField()


def is_postgres() -> bool:
    from django.db import connection

    return connection.vendor == "postgresql"


def update_search_index(product_ids):
    """Recalcula search_text (todas las BD) y search_vector (PostgreSQL)."""
    from .models import Product

    pg = is_postgres()
    for p in Product.objects.filter(pk__in=list(product_ids)).select_related("marca").prefetch_related("categorias"):
        text = p.build_search_text()
        updates = {"search_text": text}
        if pg:
            a = normalize(p.nombre)
            b = normalize(" ".join(filter(None, [p.marca.nombre if p.marca_id else "", *[c.nombre for c in p.categorias.all()]])))
            specs = " ".join(f"{k} {v}" for k, v in (p.especificaciones or {}).items())
            c = normalize(" ".join([p.sku, p.descripcion_corta, strip_tags(p.descripcion or ""), specs]))
            updates["search_vector"] = (
                SearchVector(Value(a, output_field=models.TextField()), weight="A", config=CONFIG)
                + SearchVector(Value(b, output_field=models.TextField()), weight="B", config=CONFIG)
                + SearchVector(Value(c, output_field=models.TextField()), weight="C", config=CONFIG)
            )
        Product.objects.filter(pk=p.pk).update(**updates)


def search_products(qs, term: str):
    """Filtra y anota relevancia. Devuelve un queryset con `relevancia`."""
    q = normalize(term)
    if not q:
        return qs.annotate(relevancia=Value(0.0, output_field=FloatField()))
    if is_postgres():
        query = SearchQuery(q, config=CONFIG, search_type="websearch")
        qs = qs.annotate(
            rank=SearchRank(F("search_vector"), query),
            sim=Greatest(
                TrigramWordSimilarity(q, Unaccent(Lower("nombre"))),
                TrigramWordSimilarity(q, "search_text") * Value(0.9),
            ),
        ).filter(Q(search_vector=query) | Q(sim__gte=SIM_UMBRAL) | Q(search_text__contains=q))
        return qs.annotate(relevancia=F("rank") * Value(2.0) + F("sim"))
    # Respaldo SQLite: todas las palabras deben aparecer en el texto normalizado.
    for palabra in q.split():
        qs = qs.filter(search_text__contains=palabra)
    return qs.annotate(relevancia=Value(1.0, output_field=FloatField()))


def _vocabulario():
    from .models import Brand, Category, Product, SearchLog

    def build():
        palabras = set()
        for nombre in Product.objects.filter(activo=True).values_list("nombre", flat=True):
            palabras.update(w for w in normalize(nombre).split() if len(w) >= 3)
        for nombre in Brand.objects.filter(activa=True).values_list("nombre", flat=True):
            palabras.update(w for w in normalize(nombre).split() if len(w) >= 3)
        for nombre in Category.objects.filter(activa=True).values_list("nombre", flat=True):
            palabras.update(w for w in normalize(nombre).split() if len(w) >= 3)
        for t in SearchLog.objects.filter(cantidad_resultados__gt=0).values_list("termino", flat=True)[:500]:
            palabras.update(w for w in t.split() if len(w) >= 3)
        return sorted(palabras)

    from apps.core.cache import get_version

    return cache.get_or_set(f"vocab:{get_version('menu')}", build, 600)


def did_you_mean(term: str) -> str | None:
    """Corrige cada palabra con la más parecida del vocabulario del catálogo."""
    q = normalize(term)
    if not q:
        return None
    vocab = _vocabulario()
    if is_postgres():
        # Con PostgreSQL usamos similitud de trigramas (más tolerante que difflib con palabras largas).
        from django.db import connection

        corregidas = []
        with connection.cursor() as cur:
            for w in q.split():
                if w in vocab:
                    corregidas.append(w)
                    continue
                cur.execute(
                    "SELECT palabra FROM unnest(%s::text[]) AS palabra ORDER BY similarity(palabra, %s) DESC LIMIT 1",
                    [vocab or [""], w],
                )
                row = cur.fetchone()
                corregidas.append(row[0] if row and row[0] else w)
        sugerencia = " ".join(corregidas)
    else:
        corregidas = []
        for w in q.split():
            m = difflib.get_close_matches(w, vocab, n=1, cutoff=0.6)
            corregidas.append(m[0] if m else w)
        sugerencia = " ".join(corregidas)
    return sugerencia if sugerencia and sugerencia != q else None


def popular_terms(term: str = "", limit: int = 5):
    from .models import SearchLog

    qs = SearchLog.objects.filter(cantidad_resultados__gt=0)
    q = normalize(term)
    if q:
        qs = qs.filter(termino__contains=q).exclude(termino=q)
    return list(qs.order_by("-cantidad_busquedas").values_list("termino", flat=True)[:limit])


def log_search(term: str, resultados: int):
    from .models import SearchLog

    q = normalize(term)[:120]
    if len(q) < 2:
        return
    try:
        updated = SearchLog.objects.filter(termino=q).update(
            cantidad_busquedas=F("cantidad_busquedas") + 1, cantidad_resultados=resultados, ultima_fecha=timezone.now()
        )
        if not updated:
            SearchLog.objects.get_or_create(
                termino=q, defaults={"cantidad_busquedas": 1, "cantidad_resultados": resultados}
            )
    except Exception:  # el registro nunca debe romper la búsqueda
        logger.exception("search_log_error termino=%s", q)


def suggestions(term: str, limit_products: int = 6):
    from .models import Category, Product

    q = normalize(term)
    productos = list(
        search_products(Product.objects.activos(), q).para_listado().order_by("-relevancia", "-destacado")[:limit_products]
    )
    cats = Category.objects.filter(activa=True)
    if is_postgres():
        cats = cats.annotate(sim=TrigramWordSimilarity(q, Unaccent(Lower("nombre")))).filter(
            Q(sim__gte=0.45) | Q(nombre__unaccent__icontains=q)
        ).order_by("-sim")
    else:
        cats = [c for c in cats.select_related("parent") if q in normalize(c.nombre)]
    categorias = list(cats[:4])
    return {"productos": productos, "categorias": categorias, "populares": popular_terms(q, 4)}

