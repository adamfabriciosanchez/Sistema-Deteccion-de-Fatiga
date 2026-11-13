import json
import os
import uuid
import shutil
from uuid import UUID
from datetime import datetime
from typing import List, Dict, Any, Optional
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Depends, HTTPException, status, UploadFile, File, Form
from sqlalchemy.orm import Session
from app.core.database import get_db, SessionLocal
from app.core.dependencies import get_current_user, require_roles
from app.websockets.connection_manager import manager
from app.services.telemetria_service import TelemetriaService
from app.services.rutas_oficiales import get_trazado_oficial, calcular_ruta_oficial
from app.repositories.telemetria_repo import TelemetriaRepository
from app.repositories.despacho_repo import DespachoRepository
from app.schemas.telemetria_schema import (
    TelemetriaPayload,
    TelemetriaOut,
    BusSnapshot,
    AtencionIncidenteCreate,
    AtencionIncidenteOut,
    IncidenteAlertaOut
)
from app.models.models import Usuario, RolUsuario, HojaDeRuta

router = APIRouter(tags=["Telemetría en Tiempo Real e Incidentes"])

UPLOAD_AUDIOS_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "static", "uploads", "audios")
os.makedirs(UPLOAD_AUDIOS_DIR, exist_ok=True)

# =========================================================
# WEBSOCKET: INGESTA DE TELEMETRÍA Y CÁMARA DESDE EL BUS
# =========================================================

@router.websocket("/ws/telemetry/{hoja_de_ruta_id}")
async def websocket_telemetria_bus(websocket: WebSocket, hoja_de_ruta_id: str):
    """
    Canal WebSocket para la cabina del bus / smartphone del conductor.
    Transmite telemetría GPS, métricas de fatiga en vivo, fotogramas de cámara y peticiones rápidas.
    """
    await manager.connect_telemetry(hoja_de_ruta_id, websocket)
    db = SessionLocal()
    service = TelemetriaService(db)
    try:
        while True:
            data = await websocket.receive_text()
            try:
                payload_dict = json.loads(data)

                # 1. Solicitud de asumir relevo activo de conducción (Exclusividad de Cámara)
                if payload_dict.get("tipo_evento") == "ASUMIR_RELEVO":
                    hoja_id = payload_dict.get("hoja_de_ruta_id", hoja_de_ruta_id)
                    cond_id = str(payload_dict.get("conductor_id"))
                    manager.set_active_driver(str(hoja_id), cond_id)

                    # Notificar a todas las cabinas conectadas al bus
                    await manager.send_to_telemetry(str(hoja_id), {
                        "tipo_evento": "CAMBIO_CONDUCTOR_ACTIVO",
                        "conductor_activo_id": cond_id,
                        "mensaje": "Se ha registrado el relevo. Conductor al volante actualizado."
                    })

                    # Notificar al dashboard de operadores
                    await manager.broadcast_to_dashboard({
                        "tipo_evento": "NOTIFICACION_CONDUCTOR",
                        "hoja_de_ruta_id": str(hoja_id),
                        "tipo_peticion": "CAMBIO_RELEVO",
                        "mensaje": "Cambio de turno en ruta: El Chofer de Relevo asume la conducción.",
                        "timestamp": datetime.utcnow().isoformat()
                    })

                    await websocket.send_json({"status": "RELEVO_CONFIRMADO", "conductor_activo_id": cond_id})
                    continue

                # 2. Liberación voluntaria de la cámara (al apagar la cámara)
                if payload_dict.get("tipo_evento") == "LIBERAR_VOLANTE":
                    hoja_id = payload_dict.get("hoja_de_ruta_id", hoja_de_ruta_id)
                    cond_id = str(payload_dict.get("conductor_id"))
                    manager.release_driver(str(hoja_id), cond_id)
                    await websocket.send_json({"status": "VOLANTE_LIBERADO"})
                    continue

                # 3. Petición rápida del conductor hacia el Centro de Monitoreo (Relevo / Alerta)
                if payload_dict.get("tipo_evento") == "PETICION_CONDUCTOR":
                    tipo_peticion = payload_dict.get("tipo_peticion", "ALERTA")
                    mensaje_peticion = payload_dict.get("mensaje", "Petición del conductor")
                    hoja_id = payload_dict.get("hoja_de_ruta_id", hoja_de_ruta_id)
                    await manager.broadcast_to_dashboard({
                        "tipo_evento": "NOTIFICACION_CONDUCTOR",
                        "hoja_de_ruta_id": str(hoja_id),
                        "tipo_peticion": tipo_peticion,
                        "mensaje": mensaje_peticion,
                        "timestamp": datetime.utcnow().isoformat()
                    })
                    await websocket.send_json({"status": "PETICION_RECIBIDA", "tipo": tipo_peticion})
                    continue

                # 4. Trama de telemetría y frame de visión artificial con validación de conductor activo
                payload = TelemetriaPayload(**payload_dict)
                hoja_str = str(payload.hoja_de_ruta_id)
                cond_str = str(payload.conductor_id)
                active_driver = manager.get_active_driver(hoja_str)

                # Si no hay conductor activo al volante aún, el primero que transmite toma el mando
                if not active_driver:
                    manager.set_active_driver(hoja_str, cond_str)
                    active_driver = cond_str

                # Si este conductor NO es el que está al volante, no transmitir su cámara para evitar alternancias
                if active_driver != cond_str:
                    await websocket.send_json({
                        "status": "EN_ESPERA_RELEVO",
                        "conductor_activo_id": active_driver,
                        "mensaje": "Otro conductor está al volante transmitiendo la cámara de este bus."
                    })
                    continue

                ack_response = await service.procesar_trama(payload)
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
    Canal WebSocket para la pantalla de monitoreo y centro de cámaras de los operadores y administradores.
    """
    await manager.connect_dashboard(websocket)
    try:
        while True:
            msg = await websocket.receive_text()
            if msg == "ping":
                await websocket.send_text("pong")
    except WebSocketDisconnect:
        manager.disconnect_dashboard(websocket)


# =========================================================
# ENDPOINTS REST DE CONSULTA, RUTAS OFICIALES Y PPS
# =========================================================

@router.get("/api/v1/telemetria/monitoreo-flota", response_model=List[Dict[str, Any]], summary="Flota para Centro de Monitoreo")
@router.get("/api/v1/telemetria/activas", response_model=List[Dict[str, Any]], summary="Obtener snapshot de buses activos")
def obtener_monitoreo_flota(db: Session = Depends(get_db)):
    service = TelemetriaService(db)
    return service.obtener_flota_monitoreo()

@router.get("/api/v1/telemetria/ruta-oficial/{hoja_de_ruta_id}", summary="Geometría oficial ATT de una hoja de ruta")
def obtener_ruta_oficial_hoja(hoja_de_ruta_id: UUID, db: Session = Depends(get_db)):
    hoja = db.query(HojaDeRuta).filter(HojaDeRuta.id == hoja_de_ruta_id).first()
    if not hoja:
        raise HTTPException(status_code=404, detail="Hoja de ruta no encontrada")

    coords = get_trazado_oficial(hoja.origen_ciudad, hoja.destino_ciudad, hoja.origen_terminal, hoja.destino_terminal)
    info_ruta = calcular_ruta_oficial(hoja.origen_ciudad, hoja.destino_ciudad)

    # Coordenadas en formato GeoJSON [lng, lat]
    geojson_coords = [[c[1], c[0]] for c in coords]

    return {
        "hoja_de_ruta_id": str(hoja.id),
        "codigo_hoja": hoja.codigo_hoja,
        "origen": hoja.origen_ciudad,
        "destino": hoja.destino_ciudad,
        "distancia_km": info_ruta.get("distancia_km", float(hoja.distancia_km or 0)),
        "duracion_estimada_hrs": info_ruta.get("duracion_estimada_hrs", float(hoja.duracion_estimada_hrs or 0)),
        "puntos_latlng": coords,
        "geojson": {
            "type": "Feature",
            "geometry": {
                "type": "LineString",
                "coordinates": geojson_coords
            },
            "properties": {
                "origen": hoja.origen_ciudad,
                "destino": hoja.destino_ciudad,
                "oficial_att": True
            }
        }
    }

@router.get("/api/v1/rutas/oficial/{origen}/{destino}", summary="Trazado oficial entre dos ciudades según la Red Vial Fundamental")
def obtener_ruta_oficial_ciudades(origen: str, destino: str):
    coords = get_trazado_oficial(origen, destino)
    info = calcular_ruta_oficial(origen, destino)
    geojson_coords = [[c[1], c[0]] for c in coords]
    return {
        "origen": origen,
        "destino": destino,
        "distancia_km": info.get("distancia_km", 0),
        "duracion_estimada_hrs": info.get("duracion_estimada_hrs", 0),
        "puntos_latlng": coords,
        "geojson": {
            "type": "Feature",
            "geometry": {
                "type": "LineString",
                "coordinates": geojson_coords
            }
        }
    }

@router.post("/api/v1/telemetria/peticion-conductor", summary="Envío de petición rápida del conductor por HTTP fallback")
async def recibir_peticion_conductor_http(
    hoja_de_ruta_id: UUID = Form(...),
    tipo_peticion: str = Form(...),
    mensaje: Optional[str] = Form(None),
    current_user: Usuario = Depends(get_current_user)
):
    """
    Permite al conductor transmitir peticiones rápidas (relevo, fatiga, emergencia)
    garantizadas mediante HTTP cuando el WebSocket esté en reconexión.
    """
    await manager.broadcast_to_dashboard({
        "tipo_evento": "NOTIFICACION_CONDUCTOR",
        "hoja_de_ruta_id": str(hoja_de_ruta_id),
        "tipo_peticion": tipo_peticion,
        "mensaje": mensaje or "Petición del conductor",
        "timestamp": datetime.utcnow().isoformat()
    })
    return {"status": "OK", "tipo_peticion": tipo_peticion}

@router.post("/api/v1/telemetria/asumir-relevo", summary="Asumir conducción activa por relevo vía HTTP fallback")
async def asumir_relevo_http(
    hoja_de_ruta_id: UUID = Form(...),
    conductor_id: UUID = Form(...),
    current_user: Usuario = Depends(get_current_user)
):
    hoja_str = str(hoja_de_ruta_id)
    cond_str = str(conductor_id)
    manager.set_active_driver(hoja_str, cond_str)
    await manager.send_to_telemetry(hoja_str, {
        "tipo_evento": "CAMBIO_CONDUCTOR_ACTIVO",
        "conductor_activo_id": cond_str,
        "mensaje": "Se ha registrado el relevo. Conductor al volante actualizado."
    })
    await manager.broadcast_to_dashboard({
        "tipo_evento": "NOTIFICACION_CONDUCTOR",
        "hoja_de_ruta_id": hoja_str,
        "tipo_peticion": "CAMBIO_RELEVO",
        "mensaje": "Cambio de conductor en ruta: Chofer de Relevo asume la conducción.",
        "timestamp": datetime.utcnow().isoformat()
    })
    return {"status": "RELEVO_CONFIRMADO", "conductor_activo_id": cond_str}

@router.post("/api/v1/telemetria/subir-audio-pps", summary="Subir nota de audio grabada en el Protocolo de Parada Segura")
async def subir_audio_pps(
    audio_file: UploadFile = File(...),
    current_user: Usuario = Depends(require_roles([RolUsuario.ADMIN, RolUsuario.OPERADOR]))
):
    """
    Almacena físicamente el archivo de audio grabado por el operador y retorna la URL pública.
    """
    if not audio_file:
        raise HTTPException(status_code=400, detail="Archivo de audio requerido.")

    ext = os.path.splitext(audio_file.filename)[1].lower() or ".webm"
    filename = f"pps_audio_{uuid.uuid4()}{ext}"
    dest_path = os.path.join(UPLOAD_AUDIOS_DIR, filename)

    with open(dest_path, "wb") as buffer:
        shutil.copyfileobj(audio_file.file, buffer)

    audio_url = f"/static/uploads/audios/{filename}"
    return {"audio_url": audio_url, "filename": filename}

@router.get("/api/v1/telemetria/historial/{hoja_de_ruta_id}", summary="Historial geoespacial de un viaje (Formato GeoJSON)")
def obtener_historial_geojson(hoja_de_ruta_id: UUID, db: Session = Depends(get_db)):
    repo = TelemetriaRepository(db)
    registros = repo.obtener_historial(hoja_de_ruta_id)
    coordenadas = [[float(r.longitud), float(r.latitud)] for r in registros]
    return {
        "type": "FeatureCollection",
        "features": [
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
    }

@router.post("/api/v1/telemetria/enviar", summary="Ingesta de telemetría vía REST (Fallback/Sync)")
async def enviar_telemetria_rest(payload: TelemetriaPayload, db: Session = Depends(get_db)):
    service = TelemetriaService(db)
    return await service.procesar_trama(payload)

@router.get("/api/v1/incidentes/activos", response_model=List[IncidenteAlertaOut], summary="Listar incidentes recientes")
def listar_incidentes_activos(
    limit: int = 20,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(get_current_user)
):
    repo = TelemetriaRepository(db)
    return repo.obtener_incidentes_activos(limit=limit)

@router.post("/api/v1/incidentes/atencion", response_model=AtencionIncidenteOut, status_code=status.HTTP_201_CREATED, summary="Registrar atención de incidente (Protocolo de Parada Segura)")
async def registrar_atencion_incidente(
    atencion_in: AtencionIncidenteCreate,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_roles([RolUsuario.ADMIN, RolUsuario.OPERADOR]))
):
    service = TelemetriaService(db)
    return await service.atender_incidente(atencion_in, operador_actual=current_user)
