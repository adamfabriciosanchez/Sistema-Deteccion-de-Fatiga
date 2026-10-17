import json
from uuid import UUID
from datetime import datetime
from typing import List, Dict, Any, Optional
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Depends, HTTPException, status
from sqlalchemy.orm import Session
from app.core.database import get_db, SessionLocal
from app.core.dependencies import get_current_user, require_roles
from app.websockets.connection_manager import manager
from app.services.telemetria_service import TelemetriaService
from app.repositories.telemetria_repo import TelemetriaRepository
from app.schemas.telemetria_schema import (
    TelemetriaPayload,
    TelemetriaOut,
    BusSnapshot,
    AtencionIncidenteCreate,
    AtencionIncidenteOut,
    IncidenteAlertaOut
)
from app.models.models import Usuario, RolUsuario

router = APIRouter(tags=["Telemetría en Tiempo Real e Incidentes"])

# =========================================================
# WEBSOCKET: INGESTA DE TELEMETRÍA DESDE EL BUS
# =========================================================

@router.websocket("/ws/telemetry/{hoja_de_ruta_id}")
async def websocket_telemetria_bus(websocket: WebSocket, hoja_de_ruta_id: str):
    """
    Canal WebSocket para la aplicación del bus / conductor.
    Transmite ráfagas de GPS cada 1 a 5 segundos con coordenadas y velocidad.
    """
    await manager.connect_telemetry(hoja_de_ruta_id, websocket)
    db = SessionLocal()
    service = TelemetriaService(db)
    try:
        while True:
            data = await websocket.receive_text()
            try:
                payload_dict = json.loads(data)
                payload = TelemetriaPayload(**payload_dict)
                # Procesar trama, guardar en BD y retransmitir a operadores
                ack_response = await service.procesar_trama(payload)
                # Enviar respuesta al bus
                await websocket.send_json(ack_response)
            except Exception as e:
                await websocket.send_json({"error": "Formato de trama inválido", "detalle": str(e)})
    except WebSocketDisconnect:
        manager.disconnect_telemetry(hoja_de_ruta_id, websocket)
    finally:
        db.close()


# =========================================================
# WEBSOCKET: DIFUSIÓN GENERAL HACIA EL DASHBOARD DE OPERADORES
# =========================================================

@router.websocket("/ws/dashboard")
async def websocket_dashboard(websocket: WebSocket):
    """
    Canal WebSocket para la pantalla de monitoreo de los operadores.
    Transmite la posición de toda la flota en vivo y alertas críticas.
    """
    await manager.connect_dashboard(websocket)
    try:
        while True:
            # Mantener la conexión activa recibiendo pings o mensajes del cliente
            msg = await websocket.receive_text()
            if msg == "ping":
                await websocket.send_text("pong")
    except WebSocketDisconnect:
        manager.disconnect_dashboard(websocket)


# =========================================================
# ENDPOINTS REST DE CONSULTA Y ATENCIÓN DE INCIDENTES (PPS)
# =========================================================

@router.get("/api/v1/telemetria/activas", response_model=List[Dict[str, Any]], summary="Obtener snapshot de buses activos")
def obtener_flota_activa(db: Session = Depends(get_db)):
    """
    Retorna el estado y la última posición conocida de cada bus en ruta o autorizado en terminal.
    """
    service = TelemetriaService(db)
    return service.obtener_flota_monitoreo()

@router.get("/api/v1/telemetria/monitoreo-flota", response_model=List[Dict[str, Any]], summary="Flota para Centro de Monitoreo")
def obtener_monitoreo_flota(db: Session = Depends(get_db)):
    service = TelemetriaService(db)
    return service.obtener_flota_monitoreo()

@router.get("/api/v1/telemetria/historial/{hoja_de_ruta_id}", summary="Historial geoespacial de un viaje (Formato GeoJSON)")
def obtener_historial_geojson(hoja_de_ruta_id: UUID, db: Session = Depends(get_db)):
    """
    Retorna el historial completo de telemetría de una hoja de ruta en formato GeoJSON FeatureCollection
    para trazado de ruta recorrida en Leaflet.js.
    """
    repo = TelemetriaRepository(db)
    registros = repo.obtener_historial(hoja_de_ruta_id)
    
    coordenadas = [[float(r.longitud), float(r.latitud)] for r in registros]
    
    features = [
        {
            "type": "Feature",
            "geometry": {
                "type": "LineString",
                "coordinates": coordenadas
            },
            "properties": {
                "hoja_de_ruta_id": str(hoja_de_ruta_id),
                "total_puntos": len(registros)
            }
        }
    ]

    return {
        "type": "FeatureCollection",
        "features": features
    }

@router.post("/api/v1/telemetria/enviar", summary="Ingesta de telemetría vía REST (Fallback/Sync)")
async def enviar_telemetria_rest(payload: TelemetriaPayload, db: Session = Depends(get_db)):
    """
    Endpoint HTTP para envío de telemetría en caso de reconexión o lotes offline (sync).
    """
    service = TelemetriaService(db)
    return await service.procesar_trama(payload)

@router.get("/api/v1/incidentes/activos", response_model=List[IncidenteAlertaOut], summary="Listar incidentes recientes")
def listar_incidentes_activos(
    limit: int = 20,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(get_current_user)
):
    """
    Retorna la lista de incidentes y su estado de atención.
    """
    repo = TelemetriaRepository(db)
    return repo.obtener_incidentes_activos(limit=limit)

@router.post("/api/v1/incidentes/atencion", response_model=AtencionIncidenteOut, status_code=status.HTTP_201_CREATED, summary="Registrar atención de incidente (Protocolo de Parada Segura)")
async def registrar_atencion_incidente(
    atencion_in: AtencionIncidenteCreate,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_roles([RolUsuario.ADMIN, RolUsuario.OPERADOR]))
):
    """
    Registra la atención del operador aplicando el Protocolo de Parada Segura (PPS).
    """
    service = TelemetriaService(db)
    return await service.atender_incidente(atencion_in, operador_actual=current_user)
