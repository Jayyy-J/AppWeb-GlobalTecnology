"""Cliente mínimo de Wompi (Colombia).

Firmas (verificadas contra la documentación de Wompi y el SDK @pulgueta/wompi 3.2.0):
- Integridad:  SHA256(referencia + monto_en_centavos + moneda + integrity_secret)
- Eventos:     SHA256(valores de signature.properties leídos desde `data` + timestamp + events_secret)
"""
import hashlib
import hmac
import logging

import requests
from django.conf import settings

logger = logging.getLogger("wompi")
TIMEOUT = 15


def integrity_signature(reference: str, amount_in_cents: int, currency: str = "COP", secret: str | None = None) -> str:
    secret = settings.WOMPI_INTEGRITY_SECRET if secret is None else secret
    raw = f"{reference}{int(amount_in_cents)}{currency}{secret}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _get_path(data: dict, path: str):
    cur = data
    for part in path.split("."):
        if not isinstance(cur, dict):
            return None
        cur = cur.get(part)
    return cur


def event_checksum(event: dict, secret: str | None = None) -> str:
    secret = settings.WOMPI_EVENTS_SECRET if secret is None else secret
    sig = event.get("signature") or {}
    data = event.get("data") or {}
    valores = "".join("" if (v := _get_path(data, p)) is None else str(v) for p in sig.get("properties", []))
    raw = f"{valores}{event.get('timestamp', '')}{secret}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def verify_event(event: dict, secret: str | None = None) -> bool:
    """Comparación en tiempo constante del checksum del evento."""
    recibido = str((event.get("signature") or {}).get("checksum") or "")
    if not recibido or not (event.get("signature") or {}).get("properties"):
        return False
    esperado = event_checksum(event, secret)
    return hmac.compare_digest(esperado.lower(), recibido.lower())


def checkout_fields(payment, order, redirect_url: str) -> list[tuple[str, str]]:
    """Campos del formulario GET al Web Checkout (https://checkout.wompi.co/p/)."""
    fields = [
        ("public-key", settings.WOMPI_PUBLIC_KEY),
        ("currency", payment.moneda),
        ("amount-in-cents", str(payment.monto_centavos)),
        ("reference", payment.referencia),
        ("signature:integrity", integrity_signature(payment.referencia, payment.monto_centavos, payment.moneda)),
        ("redirect-url", redirect_url),
        ("customer-data:email", order.cliente_email),
        ("customer-data:full-name", order.cliente_nombre[:120]),
        ("customer-data:phone-number", "".join(ch for ch in order.cliente_telefono if ch.isdigit())[-10:]),
        ("customer-data:phone-number-prefix", "+57"),
    ]
    if order.cliente_numero_documento:
        fields += [
            ("customer-data:legal-id", order.cliente_numero_documento),
            ("customer-data:legal-id-type", order.cliente_tipo_documento or "CC"),
        ]
    if getattr(settings, "WOMPI_ENVIAR_DIRECCION", True):
        linea = order.envio_direccion + (f", {order.envio_barrio}" if order.envio_barrio else "")
        fields += [
            ("shipping-address:address-line-1", linea[:120]),
            ("shipping-address:country", "CO"),
            ("shipping-address:region", order.envio_departamento),
            ("shipping-address:city", order.envio_municipio),
            ("shipping-address:name", order.envio_nombre[:120]),
            ("shipping-address:phone-number", "".join(ch for ch in order.envio_telefono if ch.isdigit())[-10:]),
        ]
    return fields


class WompiError(Exception):
    pass


def get_transaction(transaction_id: str) -> dict:
    """GET /transactions/{id} (endpoint público; se autentica con la llave pública)."""
    url = f"{settings.WOMPI_API_URL}/transactions/{transaction_id}"
    try:
        r = requests.get(url, headers={"Authorization": f"Bearer {settings.WOMPI_PUBLIC_KEY}"}, timeout=TIMEOUT)
    except requests.RequestException as e:
        logger.warning("wompi_api_error op=get_transaction id=%s error=%s", transaction_id, e)
        raise WompiError(str(e)) from e
    if r.status_code != 200:
        logger.warning("wompi_api_error op=get_transaction id=%s status=%s", transaction_id, r.status_code)
        raise WompiError(f"HTTP {r.status_code}")
    return r.json().get("data") or {}


def find_transactions(reference: str) -> list[dict]:
    """GET /transactions?reference=… (requiere la llave privada)."""
    url = f"{settings.WOMPI_API_URL}/transactions"
    try:
        r = requests.get(
            url, params={"reference": reference},
            headers={"Authorization": f"Bearer {settings.WOMPI_PRIVATE_KEY}"}, timeout=TIMEOUT,
        )
    except requests.RequestException as e:
        logger.warning("wompi_api_error op=find_transactions ref=%s error=%s", reference, e)
        raise WompiError(str(e)) from e
    if r.status_code != 200:
        logger.warning("wompi_api_error op=find_transactions ref=%s status=%s", reference, r.status_code)
        raise WompiError(f"HTTP {r.status_code}")
    data = r.json().get("data") or []
    return data if isinstance(data, list) else [data]
