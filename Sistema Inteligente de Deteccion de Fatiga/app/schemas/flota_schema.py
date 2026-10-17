from uuid import UUID
from datetime import date
from typing import Optional
from pydantic import BaseModel, Field
from app.models.models import EstadoVehiculo, TipoBus

class VehiculoBase(BaseModel):
    placa: str = Field(..., max_length=15, description="Placa boliviana del bus")
    numero_interno: str = Field(..., max_length=20, description="Número interno de la flota")
    marca: str = Field(..., max_length=50)
    modelo: str = Field(..., max_length=50)
    chasis: Optional[str] = Field(None, max_length=50)
    carroceria: Optional[str] = Field(None, max_length=50)
    capacidad_pasajeros: Optional[int] = Field(None, gt=0)
    tipo_bus: TipoBus = TipoBus.SEMI_CAMA
    anio_fabricacion: Optional[int] = None
    kilometraje_actual: Optional[float] = 0.0
    fecha_ultimo_mantenimiento: Optional[date] = None
    soat_vigencia: Optional[date] = None
    estado: EstadoVehiculo = EstadoVehiculo.DISPONIBLE
    foto_url: Optional[str] = None
    ubicacion_actual: Optional[str] = None

class VehiculoCreate(VehiculoBase):
    pass

class VehiculoOut(VehiculoBase):
    id: UUID

    class Config:
        from_attributes = True
