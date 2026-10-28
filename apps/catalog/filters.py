"""Filtros del listado: categoría, marca, precio, descuento, disponibilidad y especificaciones dinámicas."""
from collections import Counter, defaultdict
from dataclasses import dataclass, field

from django.db.models import Count, Q

from apps.core.templatetags.cop import format_cop

from .search import search_products

ORDENES = {
    "relevancia": "Relevancia",
    "precio_asc": "Precio: menor a mayor",
    "precio_desc": "Precio: mayor a menor",
    "nuevos": "Más nuevos",
    "descuento": "Mayor descuento",
}
MAX_VALORES_POR_CLAVE = 12


def _int(v):
    try:
        n = int(str(v).replace(".", "").replace("$", "").strip())
        return n if n >= 0 else None
    except (TypeError, ValueError):
        return None


@dataclass
class Filtros:
    q: str = ""
    marcas: list = field(default_factory=list)
    subcategorias: list = field(default_factory=list)
    precio_min: int | None = None
    precio_max: int | None = None
    descuento: bool = False
    disponible: bool = False
    especificaciones: dict = field(default_factory=dict)  # {clave: [valores]}
    orden: str = "relevancia"

    @classmethod
    def desde_request(cls, params):
        esp = defaultdict(list)
        for raw in params.getlist("esp"):
            if ":" in raw:
                k, v = raw.split(":", 1)
                if k.strip() and v.strip():
                    esp[k.strip()].append(v.strip())
        orden = params.get("orden", "")
        q = params.get("q", "").strip()[:100]
        if orden not in ORDENES:
            orden = "relevancia" if q else "nuevos"
        return cls(
            q=q,
            marcas=[m for m in params.getlist("marca") if m][:20],
            subcategorias=[c for c in params.getlist("sub") if c][:20],
            precio_min=_int(params.get("min")),
            precio_max=_int(params.get("max")),
            descuento=params.get("descuento") == "1",
            disponible=params.get("disponible") == "1",
            especificaciones=dict(esp),
            orden=orden,
        )


def aplicar(qs, f: Filtros, excluir=()):
    """Aplica los filtros (salvo los indicados en `excluir`, para calcular facetas)."""
    if f.q:
        qs = search_products(qs, f.q)
    if f.subcategorias and "sub" not in excluir:
        qs = qs.filter(categorias__slug__in=f.subcategorias).distinct()
    if f.marcas and "marca" not in excluir:
        qs = qs.filter(marca__slug__in=f.marcas)
    if f.precio_min is not None:
        qs = qs.filter(precio_final_db__gte=f.precio_min)
    if f.precio_max is not None:
        qs = qs.filter(precio_final_db__lte=f.precio_max)
    if f.descuento:
        qs = qs.filter(descuento_pct_db__gt=0)
    if f.disponible:
        qs = qs.filter(stock__gt=0)
    if "esp" not in excluir:
        for clave, valores in f.especificaciones.items():
            if "__" in clave:  # no se puede expresar como lookup de JSON
                continue
            cond = Q()
            for v in valores:  # OR dentro de la misma clave, AND entre claves
                cond |= Q(**{f"especificaciones__{clave}": v})
            qs = qs.filter(cond)
    return qs


def ordenar(qs, f: Filtros):
    if f.orden == "precio_asc":
        return qs.order_by("precio_final_db", "-id")
    if f.orden == "precio_desc":
        return qs.order_by("-precio_final_db", "-id")
    if f.orden == "descuento":
        return qs.order_by("-descuento_pct_db", "-id")
    if f.orden == "relevancia" and f.q:
        return qs.order_by("-relevancia", "-destacado", "-id")
    return qs.order_by("-creado", "-id")


def facetas(base_qs, f: Filtros, categoria=None):
    """Marcas, subcategorías y especificaciones con conteo según el resultado actual.

    Los conteos se hacen sobre una subconsulta de ids para no arrastrar las
    anotaciones de búsqueda/precio al GROUP BY.
    """
    from .models import Category, Product

    def ids(excluir):
        return aplicar(base_qs, f, excluir=excluir).values("pk")

    marcas = list(
        Product.objects.filter(pk__in=ids(("marca",)), marca__isnull=False)
        .values("marca__slug", "marca__nombre").annotate(n=Count("id")).order_by("marca__nombre")
    )
    # En una categoría se ofrecen sus subcategorías; en el resto, las categorías raíz.
    if categoria is not None:
        raiz = categoria.parent if categoria.parent_id else categoria
        cats = Category.objects.filter(parent=raiz, activa=True)
    else:
        cats = Category.objects.filter(parent__isnull=True, activa=True)
    subcats = list(
        Product.objects.filter(pk__in=ids(("sub",)), categorias__in=cats)
        .values("categorias__slug", "categorias__nombre").annotate(n=Count("id")).order_by("categorias__nombre")
    )
    # Especificaciones: se calculan en Python sobre el resultado sin filtros de especificación,
    # aplicando a cada clave los filtros de las demás claves (facetas "OR dentro, AND entre").
    filas = list(aplicar(base_qs, f, excluir=("esp",)).values_list("especificaciones", flat=True)[:2000])
    seleccion = f.especificaciones
    conteo = defaultdict(Counter)
    for specs in filas:
        if not isinstance(specs, dict):
            continue
        for clave, valor in specs.items():
            ok = all(
                specs.get(k) in vals for k, vals in seleccion.items() if k != clave
            )
            if ok:
                conteo[clave][str(valor)] += 1
    especificaciones = []
    for clave in sorted(conteo, key=lambda k: (-sum(conteo[k].values()), k)):
        valores = conteo[clave]
        if len(valores) < 2 and clave not in seleccion:
            continue  # no aporta para filtrar
        especificaciones.append({
            "clave": clave,
            "valores": [
                {"valor": v, "n": n, "activo": v in seleccion.get(clave, [])}
                for v, n in sorted(valores.items(), key=lambda x: (-x[1], x[0]))[:MAX_VALORES_POR_CLAVE]
            ],
        })
    return {"marcas": marcas, "subcategorias": subcats, "especificaciones": especificaciones[:8]}


def chips(f: Filtros, request, nombres_marca=None, nombres_sub=None):
    """Chips de filtros activos con la URL que quita cada uno."""
    resultado = []

    def sin(param, valor=None):
        p = request.GET.copy()
        p.pop("pagina", None)
        if valor is None:
            p.pop(param, None)
        else:
            vals = [v for v in p.getlist(param) if v != valor]
            p.setlist(param, vals)
        qs = p.urlencode()
        return f"{request.path}?{qs}" if qs else request.path

    if f.q:
        resultado.append({"texto": f'"{f.q}"', "url": sin("q")})
    for m in f.marcas:
        resultado.append({"texto": (nombres_marca or {}).get(m, m), "url": sin("marca", m)})
    for s in f.subcategorias:
        resultado.append({"texto": (nombres_sub or {}).get(s, s), "url": sin("sub", s)})
    if f.precio_min is not None:
        resultado.append({"texto": f"Desde {format_cop(f.precio_min)}", "url": sin("min")})
    if f.precio_max is not None:
        resultado.append({"texto": f"Hasta {format_cop(f.precio_max)}", "url": sin("max")})
    if f.descuento:
        resultado.append({"texto": "Con descuento", "url": sin("descuento")})
    if f.disponible:
        resultado.append({"texto": "Disponibles", "url": sin("disponible")})
    for clave, valores in f.especificaciones.items():
        for v in valores:
            resultado.append({"texto": f"{clave}: {v}", "url": sin("esp", f"{clave}:{v}")})
    return resultado


def hay_filtros(f: Filtros):
    return bool(
        f.marcas or f.subcategorias or f.precio_min is not None or f.precio_max is not None
        or f.descuento or f.disponible or f.especificaciones
    )

