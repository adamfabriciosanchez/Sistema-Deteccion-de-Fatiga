from uuid import UUID
from datetime import datetime
from typing import Dict, Any, Optional
from fastapi import HTTPException, status
from sqlalchemy.orm import Session
from app.repositories.telemetria_repo import TelemetriaRepository
from app.repositories.despacho_repo import DespachoRepository
from app.repositories.flota_repo import VehiculoRepository
from app.websockets.connection_manager import manager
from app.models.models import TipoIncidente, NivelRiesgo, EstadoHoja, EstadoVehiculo, Usuario, AtencionIncidente, HojaDeRuta
from app.schemas.telemetria_schema import TelemetriaPayload, IncidenteAlertaCreate, AtencionIncidenteCreate
from app.services.rutas_oficiales import get_coordenadas_ciudad

class TelemetriaService:
    def __init__(self, db: Session):
        self.db = db
        self.repo = TelemetriaRepository(db)
        self.despacho_repo = DespachoRepository(db)
        self.flota_repo = VehiculoRepository(db)

    async def procesar_trama(self, payload: TelemetriaPayload) -> Dict[str, Any]:
        """
        Procesa una ráfaga GPS recibida del bus:
        1. Persiste en base de datos PostgreSQL (registro_telemetria).
        2. Evalúa velocidad con el límite de 80 km/h y datos de fatiga:
           - Si velocidad > 80 km/h: genera incidente EXCESO_VELOCIDAD con riesgo AMARILLO.
           - Si indice_fatiga >= 0.75: genera incidente FATIGA_CRITICA con riesgo ROJO.
           - Si indice_fatiga >= 0.50: genera incidente SOMNOLENCIA_PREVENTIVA con riesgo AMARILLO.
           - Si velocidad <= 80 km/h y sin fatiga: riesgo VERDE.
        3. Actualiza el snapshot en memoria.
        4. Transmite vía WebSocket broadcast al Dashboard de los Operadores.
        """
        hoja = self.despacho_repo.get_hoja_by_id(payload.hoja_de_ruta_id)
        if not hoja:
            return {"error": "Hoja de ruta no encontrada"}

        # Si el bus no estaba EN_TRANSITO y empieza a enviar telemetría, activarlo a EN_TRANSITO
        if hoja.estado in [EstadoHoja.AUTORIZADA, EstadoHoja.PRE_DESPACHO, EstadoHoja.BORRADOR, EstadoHoja.FINALIZADA]:
            self.despacho_repo.update_estado(hoja.id, EstadoHoja.EN_TRANSITO)
            self.flota_repo.update_estado(hoja.vehiculo_id, EstadoVehiculo.EN_TRANSITO)

        # =========================================================
        # [EVENTO TELEMETRÍA 1: PERSISTENCIA EN BASE DE DATOS]
        # =========================================================
        self.repo.guardar_telemetria(payload)

        # =========================================================
        # [EVENTO TELEMETRÍA 2: EVALUACIÓN DE SEMÁFORO DE RIESGO]
        # Evalúa velocidad y también datos de fatiga (IF / PERCLOS)
        # =========================================================
        nivel_riesgo = NivelRiesgo.VERDE
        alerta_mensaje = None
        incidente_generado = None

        # Extraer datos de fatiga del payload extendido (si existen)
        indice_fatiga = getattr(payload, 'indice_fatiga_if', None)
        perclos = getattr(payload, 'perclos_porcentaje', None)

        # ---- Evaluar Fatiga Crítica (prioridad máxima) ----
        if indice_fatiga is not None and float(indice_fatiga) >= 0.75:
            nivel_riesgo = NivelRiesgo.ROJO
            alerta_mensaje = f" FATIGA CRÍTICA: IF={indice_fatiga:.2f} | PERCLOS={perclos:.1f}% | Vel: {payload.velocidad_kmh} km/h"
            incidente_generado = self.repo.guardar_incidente(
                IncidenteAlertaCreate(
                    hoja_de_ruta_id=payload.hoja_de_ruta_id,
                    conductor_id=payload.conductor_id,
                    tipo_incidente=TipoIncidente.FATIGA_CRITICA,
                    velocidad_instantanea=payload.velocidad_kmh,
                    latitud=payload.latitud,
                    longitud=payload.longitud,
                    nivel_riesgo=NivelRiesgo.ROJO,
                    alarma_disparada=True,
                    indice_fatiga_if=indice_fatiga,
                    perclos_porcentaje=perclos,
                    timestamp_evento=payload.timestamp_captura
                )
            )
        # ---- Evaluar Somnolencia Preventiva ----
        elif indice_fatiga is not None and float(indice_fatiga) >= 0.50:
            nivel_riesgo = NivelRiesgo.AMARILLO
            alerta_mensaje = f"Somnolencia preventiva: IF={indice_fatiga:.2f} | PERCLOS={perclos:.1f}%"
            incidente_generado = self.repo.guardar_incidente(
                IncidenteAlertaCreate(
                    hoja_de_ruta_id=payload.hoja_de_ruta_id,
                    conductor_id=payload.conductor_id,
                    tipo_incidente=TipoIncidente.SOMNOLENCIA_PREVENTIVA,
                    velocidad_instantanea=payload.velocidad_kmh,
                    latitud=payload.latitud,
                    longitud=payload.longitud,
                    nivel_riesgo=NivelRiesgo.AMARILLO,
                    alarma_disparada=True,
                    indice_fatiga_if=indice_fatiga,
                    perclos_porcentaje=perclos,
                    timestamp_evento=payload.timestamp_captura
                )
            )
        # ---- Evaluar Exceso de Velocidad ----
        elif float(payload.velocidad_kmh) > 80.0:
            nivel_riesgo = NivelRiesgo.AMARILLO
            alerta_mensaje = f"Exceso de velocidad: {payload.velocidad_kmh} km/h (Límite: 80 km/h)"
            incidente_generado = self.repo.guardar_incidente(
                IncidenteAlertaCreate(
                    hoja_de_ruta_id=payload.hoja_de_ruta_id,
                    conductor_id=payload.conductor_id,
                    tipo_incidente=TipoIncidente.EXCESO_VELOCIDAD,
                    velocidad_instantanea=payload.velocidad_kmh,
                    latitud=payload.latitud,
                    longitud=payload.longitud,
                    nivel_riesgo=NivelRiesgo.AMARILLO,
                    alarma_disparada=True,
                    indice_fatiga_if=indice_fatiga,
                    perclos_porcentaje=perclos,
                    timestamp_evento=payload.timestamp_captura
                )
            )

        # 3. Armar Snapshot enriquecido con datos del Bus y Conductor
        nombre_chofer = "Conductor Asignado"
        foto_conductor = None
        foto_bus = hoja.vehiculo.foto_url if hoja.vehiculo else None
        if hoja.tripulacion:
            primer_chofer = hoja.tripulacion[0].conductor
            if primer_chofer and primer_chofer.usuario:
                nombre_chofer = f"{primer_chofer.usuario.nombre} {primer_chofer.usuario.apellido}"
                foto_conductor = primer_chofer.usuario.foto_url

        snapshot = {
            "hoja_de_ruta_id": str(hoja.id),
            "codigo_hoja": hoja.codigo_hoja,
            "bus_numero_interno": hoja.vehiculo.numero_interno,
            "bus_disco": hoja.vehiculo.numero_interno,
            "bus_placa": hoja.vehiculo.placa,
            "bus_modelo": hoja.vehiculo.modelo,
            "foto_bus": foto_bus,
            "foto_conductor": foto_conductor,
            "ruta": f"{hoja.origen_ciudad} -> {hoja.destino_ciudad}",
            "conductor": nombre_chofer,
            "latitud": payload.latitud,
            "longitud": payload.longitud,
            "velocidad_kmh": float(payload.velocidad_kmh),
            "nivel_riesgo": nivel_riesgo.value,
            "alerta_mensaje": alerta_mensaje,
            "indice_fatiga": float(indice_fatiga) if indice_fatiga is not None else None,
            "perclos": float(perclos) if perclos is not None else None,
            "timestamp": payload.timestamp_captura.isoformat()
        }

        # 4. Actualizar caché en memoria
        manager.update_snapshot(str(hoja.id), snapshot)

        # 5. Broadcast a operadores en el Dashboard
        await manager.broadcast_to_dashboard({
            "tipo_evento": "TELEMETRIA_ACTUALIZADA",
            "data": snapshot
        })

        if incidente_generado:
            await manager.broadcast_to_dashboard({
                "tipo_evento": "INCIDENTE_ALERTA",
                "incidente_id": str(incidente_generado.id),
                "tipo_incidente": incidente_generado.tipo_incidente.value,
                "nivel_riesgo": incidente_generado.nivel_riesgo.value,
                "velocidad": float(incidente_generado.velocidad_instantanea),
                "indice_fatiga": float(incidente_generado.indice_fatiga_if) if incidente_generado.indice_fatiga_if else None,
                "perclos": float(incidente_generado.perclos_porcentaje) if incidente_generado.perclos_porcentaje else None,
                "timestamp": incidente_generado.timestamp_evento.isoformat(),
                "data": snapshot
            })

        # 6. Respuesta hacia el bus emisor (ACK)
        return {
            "status": "ACK",
            "nivel_riesgo": nivel_riesgo.value,
            "alerta": alerta_mensaje
        }

    async def atender_incidente(
        self,
        atencion_in: AtencionIncidenteCreate,
        operador_actual: Usuario
    ) -> AtencionIncidente:
        """
        Registra la atención de un incidente aplicando el Protocolo de Parada Segura (PPS).
        Emite una notificación WebSocket a los operadores para actualizar el estado del bus.
        """
        incidente = self.repo.obtener_incidente_por_id(atencion_in.incidente_id)
        if not incidente:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"El incidente con ID {atencion_in.incidente_id} no existe."
            )
        if incidente.atencion:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Este incidente ya fue atendido previamente."
            )

        # Guardar en atencion_incidente
        atencion = self.repo.registrar_atencion(atencion_in, operador_id=operador_actual.id)

        # Notificar a los dashboards de operadores
        await manager.broadcast_to_dashboard({
            "tipo_evento": "INCIDENTE_ATENDIDO",
            "incidente_id": str(incidente.id),
            "hoja_de_ruta_id": str(incidente.hoja_de_ruta_id),
            "accion_tomada": atencion.accion_tomada.value,
            "mensaje_enviado": atencion.mensaje_enviado,
            "audio_url": atencion.audio_url,
            "operador": f"{operador_actual.nombre} {operador_actual.apellido}"
        })

        # También enviar notificación al bus (conductor) vía WebSocket de telemetría
        hoja_id_str = str(incidente.hoja_de_ruta_id)
        await manager.send_to_telemetry(hoja_id_str, {
            "tipo_evento": "PPS_ATENCION",
            "accion_tomada": atencion.accion_tomada.value,
            "mensaje": atencion.mensaje_enviado or "Atención del operador registrada.",
            "audio_url": atencion.audio_url,
            "operador": f"{operador_actual.nombre} {operador_actual.apellido}",
            "timestamp": atencion.fecha_atencion.isoformat()
        })

        return atencion

    def obtener_flota_monitoreo(self) -> list:
        """
        Retorna la lista integral de buses para el Centro de Monitoreo:
        - Buses con telemetría en vivo registrada.
        - Buses con hoja de ruta AUTORIZADA (mostrados en gris en su terminal de origen).
        - Buses en estado EN_TRANSITO.
        """
        resultado_dict = {}

        # 1. Cargar snapshots en vivo existentes en memoria
        for snap in manager.get_all_snapshots():
            resultado_dict[snap["hoja_de_ruta_id"]] = snap

        # 2. Consultar hojas de ruta en BD que están AUTORIZADA o EN_TRANSITO
        hojas = self.db.query(HojaDeRuta).filter(
            HojaDeRuta.estado.in_([EstadoHoja.AUTORIZADA, EstadoHoja.EN_TRANSITO])
        ).all()

        for h in hojas:
            hid = str(h.id)
            if hid in resultado_dict:
                continue

            chofer_nombre = "Conductor Asignado"
            foto_conductor = None
            chofer_id = None
            for t in h.tripulacion:
                if t.tipo_conductor.value == "PRINCIPAL" and t.conductor:
                    chofer_nombre = f"{t.conductor.usuario.nombre} {t.conductor.usuario.apellido}" if t.conductor.usuario else "Conductor"
                    foto_conductor = t.conductor.usuario.foto_url if t.conductor.usuario else None
                    chofer_id = str(t.conductor_id)
                    break
                elif t.conductor:
                    chofer_nombre = f"{t.conductor.usuario.nombre} {t.conductor.usuario.apellido}" if t.conductor.usuario else "Conductor"
                    foto_conductor = t.conductor.usuario.foto_url if t.conductor.usuario else None
                    chofer_id = str(t.conductor_id)

            lat, lng = get_coordenadas_ciudad(h.origen_ciudad)

            if h.estado == EstadoHoja.EN_TRANSITO:
                ult_telemetria = self.repo.obtener_ultima_posicion(h.id)
                if ult_telemetria:
                    lat, lng = float(ult_telemetria.latitud), float(ult_telemetria.longitud)
                nivel = "VERDE"
            else:
                nivel = "GRIS"

            resultado_dict[hid] = {
                "hoja_de_ruta_id": hid,
                "codigo_hoja": h.codigo_hoja,
                "conductor_id": chofer_id,
                "bus_numero_interno": h.vehiculo.numero_interno if h.vehiculo else "--",
                "bus_disco": h.vehiculo.numero_interno if h.vehiculo else "--",
                "bus_placa": h.vehiculo.placa if h.vehiculo else "--",
                "bus_modelo": h.vehiculo.modelo if h.vehiculo else "--",
                "foto_bus": h.vehiculo.foto_url if h.vehiculo else None,
                "foto_conductor": foto_conductor,
                "ruta": f"{h.origen_ciudad} -> {h.destino_ciudad}",
                "conductor": chofer_nombre,
                "latitud": lat,
                "longitud": lng,
                "velocidad_kmh": 0.0,
                "nivel_riesgo": nivel,
                "estado_hoja": h.estado.value,
                "alerta_mensaje": None,
                "indice_fatiga": None,
                "perclos": None,
                "timestamp": (h.fecha_salida or datetime.utcnow()).isoformat()
            }

        return list(resultado_dict.values())
