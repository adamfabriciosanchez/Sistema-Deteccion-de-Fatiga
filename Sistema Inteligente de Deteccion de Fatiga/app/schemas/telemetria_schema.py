from uuid import UUID
from datetime import datetime
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field
from app.models.models import TipoIncidente, NivelRiesgo, AccionAtencion

class TelemetriaPayload(BaseModel):
    hoja_de_ruta_id: UUID
    conductor_id: UUID
    latitud: float = Field(..., ge=-90.0, le=90.0, description="Latitud GPS")
    longitud: float = Field(..., ge=-180.0, le=180.0, description="Longitud GPS")
    velocidad_kmh: float = Field(..., ge=0.0, description="Velocidad instantánea en km/h")
    timestamp_captura: datetime = Field(default_factory=datetime.utcnow)
    # Campos opcionales de fatiga (Módulo 3 simulado)
    indice_fatiga_if: Optional[float] = Field(None, ge=0.0, le=1.0, description="Índice de Fatiga normalizado 0.00-1.00")
    perclos_porcentaje: Optional[float] = Field(None, ge=0.0, le=100.0, description="PERCLOS (% cierre de ojos en 60s)")

class TelemetriaOut(BaseModel):
    id: UUID
    hoja_de_ruta_id: UUID
    conductor_id: UUID
    latitud: float
    longitud: float
    velocidad_kmh: float
    timestamp_captura: datetime

    class Config:
        from_attributes = True

class IncidenteAlertaCreate(BaseModel):
    hoja_de_ruta_id: UUID
    conductor_id: UUID
    tipo_incidente: TipoIncidente
    velocidad_instantanea: float
    latitud: float
    longitud: float
    nivel_riesgo: NivelRiesgo
    alarma_disparada: bool = False
    indice_fatiga_if: Optional[float] = None
    perclos_porcentaje: Optional[float] = None
    timestamp_evento: datetime = Field(default_factory=datetime.utcnow)

class AtencionIncidenteCreate(BaseModel):
    incidente_id: UUID
    accion_tomada: AccionAtencion
    mensaje_enviado: Optional[str] = None
    audio_url: Optional[str] = None

class AtencionIncidenteOut(BaseModel):
    id: UUID
    incidente_id: UUID
    operador_id: UUID
    accion_tomada: AccionAtencion
    mensaje_enviado: Optional[str] = None
    audio_url: Optional[str] = None
    fecha_atencion: datetime

    class Config:
        from_attributes = True

class IncidenteAlertaOut(BaseModel):
    id: UUID
    hoja_de_ruta_id: UUID
    conductor_id: UUID
    tipo_incidente: TipoIncidente
    nivel_riesgo: NivelRiesgo
    velocidad_instantanea: float
    latitud: float
    longitud: float
    alarma_disparada: bool
    indice_fatiga_if: Optional[float] = None
    perclos_porcentaje: Optional[float] = None
    timestamp_evento: datetime
    atencion: Optional[AtencionIncidenteOut] = None

    class Config:
        from_attributes = True

class BusSnapshot(BaseModel):
    hoja_de_ruta_id: str
    codigo_hoja: str
    bus_numero_interno: str
    bus_placa: str
    bus_modelo: Optional[str] = None
    foto_bus: Optional[str] = None
    foto_conductor: Optional[str] = None
    ruta: str
    conductor: str
    latitud: float
    longitud: float
    velocidad_kmh: float
    nivel_riesgo: str
    alerta_mensaje: Optional[str] = None
    indice_fatiga: Optional[float] = None
    perclos: Optional[float] = None
    timestamp: str
