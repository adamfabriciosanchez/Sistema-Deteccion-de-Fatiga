from uuid import UUID
from datetime import datetime
from typing import Optional
from pydantic import BaseModel, EmailStr, Field
from app.models.models import RolUsuario

class LoginRequest(BaseModel):
    email: EmailStr
    password: str

class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    rol: RolUsuario
    nombre_completo: str

class UsuarioBase(BaseModel):
    ci: str
    nombre: str
    apellido: str
    email: EmailStr
    rol: RolUsuario
    estado: bool = True

class UsuarioCreate(UsuarioBase):
    password: str = Field(..., min_length=6)

class ConductorBase(BaseModel):
    licencia_conducir: str
    categoria_licencia: str
    telefono_emergencia: Optional[str] = None
    puntaje_promedio: Optional[float] = 5.00
    ubicacion_actual: Optional[str] = None

class ConductorOut(ConductorBase):
    id: UUID

    class Config:
        from_attributes = True

class UsuarioOut(UsuarioBase):
    id: UUID
    fecha_creacion: datetime
    conductor: Optional[ConductorOut] = None

    class Config:
        from_attributes = True
