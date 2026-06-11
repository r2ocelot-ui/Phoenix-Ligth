"""Endpoints de tarifa eléctrica (tramos) para el dimming consciente de coste.

Sólo informativo/consulta: el panel puede mostrar "ahora estamos en Punta,
tope 75%". La política se aplica al dimming vía
``dimming_controller.resolve_level_cost_aware`` cuando se cablee el
auto-dimming. Todo offline.
"""
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status

from app.core.config import settings
from app.models.user import User
from app.services import ranks, tariff
from app.services.auth import require_permission

router = APIRouter(prefix="/tariff", tags=["tariff"])


@router.get("/now")
def tariff_now(
    at: str | None = None,
    _: User = Depends(require_permission(ranks.P_CABINET_READ)),
) -> dict:
    """Periodo tarifario actual (o de ``at``, ISO en hora local) + su tope."""
    try:
        when = datetime.fromisoformat(at) if at else tariff.now_local()
    except ValueError:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Fecha 'at' inválida (usa ISO-8601)")
    period = tariff.current_period(when)
    return {
        "at": when.isoformat(),
        "timezone": settings.tariff_timezone,
        "period": period,
        "label": tariff.PERIOD_LABELS[period],
        "level_cap": tariff.LEVEL_CAP[period],
        "floor": settings.tariff_floor_level,
        "enabled": settings.tariff_enabled,
    }


@router.get("/schedule")
def tariff_schedule(
    _: User = Depends(require_permission(ranks.P_CABINET_READ)),
) -> dict:
    """Calendario de tramos (laborable/finde) + etiquetas y topes, para
    pintar la franja horaria en el panel."""
    return {
        "labels": tariff.PERIOD_LABELS,
        "level_cap": tariff.LEVEL_CAP,
        "floor": settings.tariff_floor_level,
        "enabled": settings.tariff_enabled,
        "workday": list(tariff.WORKDAY_PERIODS),
        "weekend": list(tariff.WEEKEND_PERIODS),
    }
