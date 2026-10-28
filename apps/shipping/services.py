"""Cálculo de costos de envío.

`calcular_envio` es una función pura: recibe la configuración y las tarifas ya
resueltas y no toca la base de datos. `cotizar_envio` es el envoltorio que las
carga desde la BD.
"""
from dataclasses import dataclass

from apps.core.templatetags.cop import format_cop

GRATIS = "gratis"
MUNICIPIO = "municipio"
DEPARTAMENTO = "departamento"
FIJA = "fija"
COTIZACION = "cotizacion"
SIN_COBERTURA = "sin_cobertura"


@dataclass(frozen=True)
class ShippingQuote:
    codigo: str
    valor: int | None
    regla: str
    dias: str = ""

    @property
    def requiere_cotizacion(self) -> bool:
        return self.codigo == COTIZACION

    @property
    def disponible(self) -> bool:
        return self.codigo != SIN_COBERTURA


@dataclass(frozen=True)
class Tarifa:
    valor: int
    dias: str = ""


def calcular_envio(
    subtotal: int,
    config,
    destino_municipio: str = "",
    destino_departamento: str = "",
    tarifa_municipio: Tarifa | None = None,
    tarifa_departamento: Tarifa | None = None,
) -> ShippingQuote:
    """Aplica las reglas en orden de prioridad (ver SPEC §3 shipping)."""
    if config.envio_gratis_activo and subtotal >= config.envio_gratis_desde:
        return ShippingQuote(GRATIS, 0, f"Envío gratis por compras desde {format_cop(config.envio_gratis_desde)}")
    if config.tarifas_por_zona_activas and tarifa_municipio is not None:
        return ShippingQuote(
            MUNICIPIO, tarifa_municipio.valor,
            f"Envío a {destino_municipio}: {format_cop(tarifa_municipio.valor)}", tarifa_municipio.dias,
        )
    if config.tarifas_por_zona_activas and tarifa_departamento is not None:
        return ShippingQuote(
            DEPARTAMENTO, tarifa_departamento.valor,
            f"Envío a {destino_departamento}: {format_cop(tarifa_departamento.valor)}", tarifa_departamento.dias,
        )
    if config.tarifa_fija_activa:
        return ShippingQuote(FIJA, config.tarifa_fija_valor, f"Tarifa fija de envío: {format_cop(config.tarifa_fija_valor)}")
    if config.cotizacion_manual_activa:
        return ShippingQuote(
            COTIZACION, None,
            f"El envío a {destino_municipio or 'tu destino'} se cotiza manualmente: te enviaremos el valor por email.",
        )
    return ShippingQuote(SIN_COBERTURA, None, f"Por ahora no realizamos envíos a {destino_municipio or 'ese destino'}.")


def cotizar_envio(subtotal: int, municipio) -> ShippingQuote:
    """Carga configuración y tarifas desde la BD para el municipio dado."""
    from .models import ShippingSettings, ShippingZoneRate

    config = ShippingSettings.load()
    t_mun = t_dep = None
    if config.tarifas_por_zona_activas:
        rates = ShippingZoneRate.objects.filter(activo=True, departamento_id=municipio.departamento_id)
        for r in rates:
            if r.municipio_id == municipio.id:
                t_mun = Tarifa(r.valor, r.dias_estimados)
            elif r.municipio_id is None:
                t_dep = Tarifa(r.valor, r.dias_estimados)
    return calcular_envio(
        subtotal, config,
        destino_municipio=municipio.nombre, destino_departamento=municipio.departamento.nombre,
        tarifa_municipio=t_mun, tarifa_departamento=t_dep,
    )
