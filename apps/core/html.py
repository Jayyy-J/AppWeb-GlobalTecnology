import nh3

ALLOWED_TAGS = {
    "p", "br", "strong", "b", "em", "i", "u", "ul", "ol", "li", "h2", "h3", "h4",
    "a", "blockquote", "table", "thead", "tbody", "tr", "th", "td", "hr", "span",
}
ALLOWED_ATTRIBUTES = {"a": {"href", "title"}, "td": {"colspan"}, "th": {"colspan"}}


def sanitize_html(value: str) -> str:
    """Sanea HTML de texto enriquecido básico (descripciones, páginas legales)."""
    return nh3.clean(
        value or "",
        tags=ALLOWED_TAGS,
        attributes=ALLOWED_ATTRIBUTES,
        url_schemes={"http", "https", "mailto", "tel"},
        link_rel="noopener noreferrer nofollow",
    )
