from uuid import UUID
from datetime import datetime
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field
from app.models.models import EstadoHoja, TipoConductor
from app.schemas.flota_schema import VehiculoOut
from app.schemas.usuario_schema import ConductorOut

class TripulanteAsignacion(BaseModel):
    conductor_id: UUID
    tipo_conductor: TipoConductor

class AsignacionTripulacionOut(BaseModel):
    id: UUID
    conductor_id: UUID
    tipo_conductor: TipoConductor
    fecha_asignacion: datetime
    conductor: Optional[ConductorOut] = None

    class Config:
        from_attributes = True

class HojaDeRutaCreate(BaseModel):
    codigo_hoja: str = Field(..., max_length=30)
    vehiculo_id: UUID
    origen_ciudad: str = Field(..., max_length=50)
    origen_terminal: str = Field(..., max_length=100)
    destino_ciudad: str = Field(..., max_length=50)
    destino_terminal: str = Field(..., max_length=100)
    terminales_intermedias: Optional[List[str]] = None
    distancia_km: Optional[float] = None
    duracion_estimada_hrs: Optional[float] = None
    fecha_salida: datetime
    fecha_llegada_estimada: datetime
    tripulantes: List[TripulanteAsignacion] = Field(..., min_length=1)

class PreDespachoOut(BaseModel):
    id: UUID
    hoja_de_ruta_id: UUID
    operador_terminal_id: UUID
    resultado_alcotest: float
    resultado_alcotest_principal: Optional[float] = None
    aprobado_principal: Optional[bool] = None
    resultado_alcotest_relevo: Optional[float] = None
    aprobado_relevo: Optional[bool] = None
    aprobado: bool
    observaciones: Optional[str] = None
    fecha_validacion: datetime

    class Config:
        from_attributes = True

class HojaDeRutaOut(BaseModel):
    id: UUID
    codigo_hoja: str
    vehiculo_id: UUID
    origen_ciudad: str
    origen_terminal: str
    destino_ciudad: str
    destino_terminal: str
    terminales_intermedias: Optional[List[str]] = None
    distancia_km: Optional[float] = None
    duracion_estimada_hrs: Optional[float] = None
    fecha_salida: datetime
    fecha_llegada_estimada: datetime
    fecha_inicio_real: Optional[datetime] = None
    fecha_fin_real: Optional[datetime] = None
    duracion_real_hrs: Optional[float] = None
    estado: EstadoHoja
    vehiculo: Optional[VehiculoOut] = None
    tripulacion: List[AsignacionTripulacionOut] = []
    pre_despacho: Optional[PreDespachoOut] = None

    class Config:
        from_attributes = True

class PreDespachoCreate(BaseModel):
    hoja_de_ruta_id: UUID
    resultado_alcotest: Optional[float] = Field(default=0.0, ge=0.0)
    resultado_alcotest_principal: Optional[float] = Field(default=0.0, ge=0.0)
    resultado_alcotest_relevo: Optional[float] = Field(default=None, ge=0.0)
    observaciones: Optional[str] = None

class HojaDeRutaReasignarConductor(BaseModel):
    hoja_de_ruta_id: Optional[UUID] = None
    tipo_conductor: TipoConductor
    nuevo_conductor_id: UUID
