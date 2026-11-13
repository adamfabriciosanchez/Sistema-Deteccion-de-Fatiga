import re
from uuid import UUID
from datetime import datetime
from typing import Optional
from pydantic import BaseModel, EmailStr, Field, field_validator
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
    ci: str = Field(..., min_length=4, max_length=20)
    nombre: str = Field(..., min_length=2, max_length=100)
    apellido: str = Field(..., min_length=2, max_length=100)
    email: EmailStr
    rol: RolUsuario
    telefono: Optional[str] = Field(None, max_length=20)
    tipo_sangre: Optional[str] = Field(None, max_length=10)
    departamento: Optional[str] = Field(None, max_length=50)
    terminal_asignada: Optional[str] = Field(None, max_length=100)
    foto_url: Optional[str] = None
    estado: bool = True

    @field_validator("nombre", "apellido")
    @classmethod
    def validar_nombres(cls, v: str) -> str:
        v_clean = v.strip()
        if not re.match(r"^[A-Za-zÁÉÍÓÚáéíóúñÑüÜ\s'-]{2,100}$", v_clean):
            raise ValueError("El campo solo debe contener letras y espacios, sin números ni símbolos especiales.")
        return v_clean

    @field_validator("ci")
    @classmethod
    def validar_ci(cls, v: str) -> str:
        v_clean = v.strip().upper()
        if not re.match(r"^[0-9]{4,10}(-[0-9A-Z]{1,2})?$", v_clean):
            raise ValueError("El CI debe ser un documento válido boliviano (ej. 5550001 o 5550001-1A).")
        return v_clean

    @field_validator("telefono")
    @classmethod
    def validar_telefono(cls, v: Optional[str]) -> Optional[str]:
        if not v:
            return None
        v_clean = v.strip()
        if not re.match(r"^[67][0-9]{7}$", v_clean):
            raise ValueError("El teléfono celular debe ser boliviano de 8 dígitos y comenzar con 6 o 7.")
        return v_clean

    @field_validator("tipo_sangre")
    @classmethod
    def validar_tipo_sangre(cls, v: Optional[str]) -> Optional[str]:
        if not v:
            return None
        v_clean = v.strip().upper()
        validos = ["O+", "O-", "A+", "A-", "B+", "B-", "AB+", "AB-"]
        if v_clean not in validos:
            raise ValueError(f"Tipo de sangre no válido. Opciones: {', '.join(validos)}.")
        return v_clean

class UsuarioCreate(UsuarioBase):
    password: str = Field(..., min_length=6)

class ConductorBase(BaseModel):
    licencia_conducir: str = Field(..., min_length=4, max_length=30)
    categoria_licencia: str = Field(..., min_length=1, max_length=30)
    telefono_emergencia: Optional[str] = None
    contacto_emergencia_nombre: Optional[str] = None
    puntaje_promedio: Optional[float] = 0.00
    viajes_concluidos: Optional[int] = 0
    ubicacion_actual: Optional[str] = None

    @field_validator("contacto_emergencia_nombre")
    @classmethod
    def validar_contacto(cls, v: Optional[str]) -> Optional[str]:
        if not v:
            return None
        v_clean = v.strip()
        if not re.match(r"^[A-Za-zÁÉÍÓÚáéíóúñÑüÜ\s'-]{2,100}$", v_clean):
            raise ValueError("El nombre del contacto de emergencia solo debe contener letras.")
        return v_clean

    @field_validator("telefono_emergencia")
    @classmethod
    def validar_tel_emergencia(cls, v: Optional[str]) -> Optional[str]:
        if not v:
            return None
        v_clean = v.strip()
        if not re.match(r"^[67][0-9]{7}$", v_clean):
            raise ValueError("El teléfono de emergencia debe ser un celular de 8 dígitos comenzando con 6 o 7.")
        return v_clean

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
