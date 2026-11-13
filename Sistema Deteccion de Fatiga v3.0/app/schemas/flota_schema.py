import re
from uuid import UUID
from datetime import date
from typing import Optional
from pydantic import BaseModel, Field, field_validator
from app.models.models import EstadoVehiculo, TipoBus

class VehiculoBase(BaseModel):
    placa: str = Field(..., max_length=15, description="Placa boliviana del bus")
    numero_interno: str = Field(..., max_length=20, description="Número interno de la flota TC-XXX")
    marca: str = Field(..., max_length=50)
    modelo: str = Field(..., max_length=50)
    chasis: Optional[str] = Field(None, max_length=50)
    carroceria: Optional[str] = Field(None, max_length=50)
    capacidad_pasajeros: Optional[int] = Field(None, gt=0)
    tipo_bus: TipoBus = TipoBus.SEMI_CAMA
    anio_fabricacion: Optional[int] = None
    kilometraje_actual: Optional[float] = 0.0
    fecha_ultimo_mantenimiento: Optional[date] = None
    soat_numero: Optional[str] = Field(None, max_length=30)
    soat_vigencia: Optional[date] = None
    estado: EstadoVehiculo = EstadoVehiculo.DISPONIBLE
    foto_url: Optional[str] = None
    ubicacion_actual: Optional[str] = None
    terminal_actual: Optional[str] = None

    @field_validator("numero_interno")
    @classmethod
    def validar_numero_interno(cls, v: str) -> str:
        v_clean = v.strip().upper()
        if not re.match(r"^TC-[0-9]{2,4}$", v_clean):
            raise ValueError("El número interno debe tener el formato oficial TC-XXX (ej. TC-010).")
        return v_clean

    @field_validator("placa")
    @classmethod
    def validar_placa(cls, v: str) -> str:
        v_clean = v.strip().upper()
        if not re.match(r"^[0-9]{3,4}-?[A-Z]{3}$", v_clean):
            raise ValueError("La placa debe tener formato boliviano válido (ej. 4512-PTY o 1001-LPZ).")
        if "-" not in v_clean:
            # Normalizar insertando el guión si viene continuo
            v_clean = f"{v_clean[:-3]}-{v_clean[-3:]}"
        return v_clean

    @field_validator("marca")
    @classmethod
    def validar_marca(cls, v: str) -> str:
        v_clean = v.strip()
        marcas_validas = ["Mercedes-Benz", "Scania", "Volvo", "MAN", "Marcopolo"]
        if v_clean not in marcas_validas:
            raise ValueError(f"Marca no autorizada. Seleccione una de: {', '.join(marcas_validas)}.")
        return v_clean

    @field_validator("soat_numero")
    @classmethod
    def validar_soat_numero(cls, v: Optional[str]) -> Optional[str]:
        if not v:
            return None
        v_clean = v.strip().upper()
        if not re.match(r"^[A-Z0-9-]{5,30}$", v_clean):
            raise ValueError("El número de SOAT debe tener entre 5 y 30 caracteres alfanuméricos.")
        return v_clean

class VehiculoCreate(VehiculoBase):
    pass

class VehiculoOut(VehiculoBase):
    id: UUID

    class Config:
        from_attributes = True
