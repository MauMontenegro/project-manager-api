"""Tiempo hábil según el calendario laboral (Configuración) y la zona horaria de la empresa.

- Día hábil: lunes a viernes con `horas_entre_semana` > 0, sábado si `horas_sabado` > 0; nunca domingo
  ni los días inactivos.
- Duración de un periodo (bloqueos): por cada día hábil que toca, las horas cubiertas, hasta la jornada de
  ese día (`horas_entre_semana` o `horas_sabado`). Un día hábil completo vale 1 día y su jornada; medio
  día de jornada, 0.5. Fines de semana e inactivos no cuentan.
- Varios periodos de una misma tarea se unen antes de medirlos: dos bloqueos simultáneos no cuentan doble.
"""
from datetime import date, datetime, time, timedelta
from decimal import Decimal
from functools import lru_cache
from zoneinfo import ZoneInfo

from app.core.config import settings
from app.models.configuracion import ConfiguracionLaboral

DOS = Decimal("0.01")


@lru_cache
def zona() -> ZoneInfo:
    return ZoneInfo(settings.ZONA_HORARIA)


def ahora() -> datetime:
    return datetime.now(zona())


def hoy() -> date:
    return ahora().date()


def fecha_local(momento: datetime) -> date:
    return momento.astimezone(zona()).date()


def horas_dia(config: ConfiguracionLaboral, dia: date) -> Decimal:
    """Horas de jornada del día (0 si no es hábil)."""
    if dia.weekday() == 6 or dia in set(config.dias_inactivos):
        return Decimal(0)
    return config.horas_entre_semana if dia.weekday() < 5 else config.horas_sabado


def es_habil(config: ConfiguracionLaboral, dia: date) -> bool:
    return horas_dia(config, dia) > 0


def dias_habiles_entre(config: ConfiguracionLaboral, desde: date, hasta: date) -> int:
    """Días hábiles de `desde` (excluido) a `hasta` (incluido); negativo si `hasta` es anterior. Mide cuánto se
    movió una fecha: de un viernes al lunes siguiente es 1."""
    if hasta == desde:
        return 0
    signo, a, b = (1, desde, hasta) if hasta > desde else (-1, hasta, desde)
    n, dia = 0, a + timedelta(days=1)
    while dia <= b:
        n += es_habil(config, dia)
        dia += timedelta(days=1)
    return signo * n


def unir(periodos: list[tuple[datetime, datetime]]) -> list[tuple[datetime, datetime]]:
    """Une los periodos que se enciman o se tocan."""
    unidos: list[tuple[datetime, datetime]] = []
    for inicio, fin in sorted(periodos):
        if unidos and inicio <= unidos[-1][1]:
            unidos[-1] = (unidos[-1][0], max(unidos[-1][1], fin))
        else:
            unidos.append((inicio, fin))
    return unidos


def duracion_habil(config: ConfiguracionLaboral, periodos: list[tuple[datetime, datetime]]) -> tuple[Decimal, Decimal]:
    """(días hábiles, horas hábiles) que cubren los periodos, unidos primero."""
    tz = zona()
    dias = horas = Decimal(0)
    for inicio, fin in unir(periodos):
        inicio, fin = inicio.astimezone(tz), fin.astimezone(tz)
        dia = inicio.date()
        while dia <= fin.date():
            h = horas_dia(config, dia)
            if h > 0:
                desde = max(inicio, datetime.combine(dia, time.min, tz))
                hasta = min(fin, datetime.combine(dia + timedelta(days=1), time.min, tz))
                cubiertas = min(Decimal(str(max((hasta - desde).total_seconds(), 0) / 3600)), h)
                horas += cubiertas
                dias += cubiertas / h
            dia += timedelta(days=1)
    return dias.quantize(DOS), horas.quantize(DOS)
