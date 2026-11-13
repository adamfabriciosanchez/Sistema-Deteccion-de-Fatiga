from typing import List, Optional
from uuid import UUID
from datetime import datetime
from sqlalchemy.orm import Session, joinedload
from app.models.models import (
    RegistroTelemetria,
    IncidenteAlerta,
    AtencionIncidente,
    TipoIncidente,
    NivelRiesgo,
    AccionAtencion,
    HojaDeRuta
)
from app.schemas.telemetria_schema import TelemetriaPayload, IncidenteAlertaCreate, AtencionIncidenteCreate

class TelemetriaRepository:
    def __init__(self, db: Session):
        self.db = db

    def guardar_telemetria(self, payload: TelemetriaPayload) -> RegistroTelemetria:
        db_tele = RegistroTelemetria(
            hoja_de_ruta_id=payload.hoja_de_ruta_id,
            conductor_id=payload.conductor_id,
            latitud=payload.latitud,
            longitud=payload.longitud,
            velocidad_kmh=payload.velocidad_kmh,
            timestamp_captura=payload.timestamp_captura,
            timestamp_sync=datetime.utcnow()
        )
        self.db.add(db_tele)
        self.db.commit()
        self.db.refresh(db_tele)
        return db_tele

    def guardar_incidente(self, inc_in: IncidenteAlertaCreate) -> IncidenteAlerta:
        db_inc = IncidenteAlerta(
            hoja_de_ruta_id=inc_in.hoja_de_ruta_id,
            conductor_id=inc_in.conductor_id,
            tipo_incidente=inc_in.tipo_incidente,
            velocidad_instantanea=inc_in.velocidad_instantanea,
            latitud=inc_in.latitud,
            longitud=inc_in.longitud,
            nivel_riesgo=inc_in.nivel_riesgo,
            alarma_disparada=inc_in.alarma_disparada,
            indice_fatiga_if=inc_in.indice_fatiga_if,
            perclos_porcentaje=inc_in.perclos_porcentaje,
            timestamp_evento=inc_in.timestamp_evento,
            estado_sync=True
        )
        self.db.add(db_inc)
        self.db.commit()
        self.db.refresh(db_inc)
        return db_inc

    def obtener_incidente_por_id(self, incidente_id: UUID) -> Optional[IncidenteAlerta]:
        return (
            self.db.query(IncidenteAlerta)
            .options(
                joinedload(IncidenteAlerta.hoja_de_ruta).joinedload(HojaDeRuta.vehiculo),
                joinedload(IncidenteAlerta.atencion)
            )
            .filter(IncidenteAlerta.id == incidente_id)
            .first()
        )

    def registrar_atencion(
        self,
        atencion_in: AtencionIncidenteCreate,
        operador_id: UUID
    ) -> AtencionIncidente:
        db_atencion = AtencionIncidente(
            incidente_id=atencion_in.incidente_id,
            operador_id=operador_id,
            accion_tomada=atencion_in.accion_tomada,
            mensaje_enviado=atencion_in.mensaje_enviado,
            audio_url=atencion_in.audio_url,
            fecha_atencion=datetime.utcnow()
        )
        self.db.add(db_atencion)
        self.db.commit()
        self.db.refresh(db_atencion)
        return db_atencion

    def obtener_historial(self, hoja_id: UUID) -> List[RegistroTelemetria]:
        return (
            self.db.query(RegistroTelemetria)
            .filter(RegistroTelemetria.hoja_de_ruta_id == hoja_id)
            .order_by(RegistroTelemetria.timestamp_captura.asc())
            .all()
        )

    def obtener_incidentes_activos(self, limit: int = 30) -> List[IncidenteAlerta]:
        """
        Retorna incidentes pendientes de atención o recientes ordenados por fecha descendente.
        """
        return (
            self.db.query(IncidenteAlerta)
            .options(
                joinedload(IncidenteAlerta.hoja_de_ruta).joinedload(HojaDeRuta.vehiculo),
                joinedload(IncidenteAlerta.atencion)
            )
            .order_by(IncidenteAlerta.timestamp_evento.desc())
            .limit(limit)
            .all()
        )

    def obtener_ultima_posicion(self, hoja_id: UUID) -> Optional[RegistroTelemetria]:
        """
        Retorna el último registro de telemetría de una hoja de ruta.
        """
        return (
            self.db.query(RegistroTelemetria)
            .filter(RegistroTelemetria.hoja_de_ruta_id == hoja_id)
            .order_by(RegistroTelemetria.timestamp_captura.desc())
            .first()
        )

