from django.core.files import File

from .models import AuditLog


def _valor(v):
    if hasattr(v, "pk"):
        return str(v)
    if isinstance(v, File) or hasattr(v, "url"):
        return getattr(v, "name", "") or ""
    if hasattr(v, "all"):
        return ", ".join(str(x) for x in v.all())
    if isinstance(v, (list, tuple, set)):
        return ", ".join(str(x) for x in v)
    if isinstance(v, (dict, int, float, bool)) or v is None:
        return v
    return str(v)


def cambios_de_form(form, antes: dict | None = None):
    """{campo: [antes, después]} de los campos que cambiaron en un ModelForm."""
    antes = antes or {}
    out = {}
    for name in form.changed_data:
        if name not in form.cleaned_data:
            continue
        out[name] = [_valor(antes.get(name, form.initial.get(name))), _valor(form.cleaned_data[name])]
    return out


def snapshot(instance, campos):
    return {c: _valor(getattr(instance, c, None)) for c in campos}


def registrar(request, accion, obj=None, cambios=None, modelo=None):
    ip = request.META.get("HTTP_X_FORWARDED_FOR", "").split(",")[0].strip() or request.META.get("REMOTE_ADDR")
    try:
        AuditLog.objects.create(
            usuario=request.user if request.user.is_authenticated else None,
            accion=accion,
            modelo=modelo or (obj._meta.verbose_name if obj is not None else ""),
            objeto_id=str(getattr(obj, "pk", "") or ""),
            objeto_repr=str(obj)[:200] if obj is not None else "",
            cambios=cambios or {},
            ip=ip or None,
        )
    except Exception:  # la auditoría nunca debe romper la operación
        import logging

        logging.getLogger("panel").exception("auditoria_error accion=%s", accion)
