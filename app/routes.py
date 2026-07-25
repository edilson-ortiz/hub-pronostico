from fastapi import APIRouter, HTTPException, Query
from app.ventusky_service import VentuskyService

router = APIRouter(prefix="/forecast", tags=["forecast"])


async def _build_service(lat: float, lon: float) -> VentuskyService:
    svc = VentuskyService(lat, lon)
    try:
        await svc.load_forecast()
    except Exception as e:
        raise HTTPException(status_code=502, detail=str(e))
    return svc


@router.get("/hourly")
async def forecast_hourly(
    lat: float = Query(..., description="Latitud", example=-17.783),
    lon: float = Query(..., description="Longitud", example=-63.182),
):
    """Pronóstico hora a hora (8 horarios por día)."""
    svc = await _build_service(lat, lon)
    return {
        "location": svc.note,
        "data": svc.get_forecast_hourly()
    }


@router.get("/daily")
async def forecast_daily(
    lat: float = Query(..., description="Latitud", example=-17.783),
    lon: float = Query(..., description="Longitud", example=-63.182),
):
    """Resumen diario: min/max temperatura, lluvia, viento."""
    svc = await _build_service(lat, lon)
    return {
        "location": svc.note,
        "data": svc.get_forecast_daily()
    }


@router.get("/tramos")
async def forecast_tramos(
    lat: float = Query(..., description="Latitud", example=-17.783),
    lon: float = Query(..., description="Longitud", example=-63.182),
):
    """Pronóstico dividido en tramos: madrugada, mañana, tarde, noche."""
    svc = await _build_service(lat, lon)
    return {
        "location": svc.note,
        "data": svc.get_forecast_by_tramos()
    }

@router.get("/next24h")
async def forecast_next_24h(
    lat: float = Query(..., description="Latitud", example=-17.783),
    lon: float = Query(..., description="Longitud", example=-63.182),
):
    """Pronóstico hora a hora para las próximas 24 horas (ventana móvil)."""
    svc = await _build_service(lat, lon)
    return {
        "location": svc.note,
        "data": svc.get_forecast_next_24h()
    }

@router.get("/daytramo")
async def forecast_tramos(
    lat: float = Query(..., description="Latitud", example=-17.783),
    lon: float = Query(..., description="Longitud", example=-63.182),
):
    """
    Pronostico divido en dias y luego en tramos: madrugada, mañana, tarde, noche."""
    svc = await _build_service(lat, lon)
    return {
        "location": svc.note,
        "daily": svc.get_forecast_daily(),
        "tramo": svc.get_forecast_by_tramos()
        
    }