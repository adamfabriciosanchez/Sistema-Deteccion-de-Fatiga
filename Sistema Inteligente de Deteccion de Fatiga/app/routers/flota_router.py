from typing import List, Optional
from uuid import UUID
from fastapi import APIRouter, Depends, status, Form, HTTPException
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.core.dependencies import get_current_user, require_roles
from app.models.models import RolUsuario, Usuario, EstadoVehiculo
from app.schemas.flota_schema import VehiculoCreate, VehiculoOut
from app.schemas.usuario_schema import ConductorOut
from app.repositories.flota_repo import VehiculoRepository
from app.repositories.usuario_repo import UsuarioRepository

router = APIRouter(tags=["Flota de Vehículos"])

@router.get("/vehiculos", response_model=List[VehiculoOut], summary="Listar todos los buses de la flota")
def listar_vehiculos(
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(get_current_user)
):
    repo = VehiculoRepository(db)
    return repo.list_all()

@router.post("/vehiculos", response_model=VehiculoOut, status_code=status.HTTP_201_CREATED, summary="Registrar nuevo bus vía REST (Solo Admin)")
def crear_vehiculo_rest(
    vehiculo_in: VehiculoCreate,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_roles([RolUsuario.ADMIN]))
):
    repo = VehiculoRepository(db)
    return repo.create(vehiculo_in)

@router.put("/vehiculos/{vehiculo_id}", response_model=VehiculoOut, summary="Actualizar bus de flota (Solo Admin)")
def actualizar_vehiculo_rest(
    vehiculo_id: UUID,
    vehiculo_in: VehiculoCreate,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_roles([RolUsuario.ADMIN]))
):
    repo = VehiculoRepository(db)
    bus = repo.get_by_id(vehiculo_id)
    if not bus:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Vehículo no encontrado")

    if bus.estado == EstadoVehiculo.EN_TRANSITO and vehiculo_in.estado != EstadoVehiculo.EN_TRANSITO:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No se puede cambiar el estado de un vehículo que se encuentra EN TRÁNSITO."
        )

    updated = repo.update(
        vehiculo_id,
        numero_interno=vehiculo_in.numero_interno,
        placa=vehiculo_in.placa,
        marca=vehiculo_in.marca,
        modelo=vehiculo_in.modelo,
        chasis=vehiculo_in.chasis,
        carroceria=vehiculo_in.carroceria,
        tipo_bus=vehiculo_in.tipo_bus,
        capacidad_pasajeros=vehiculo_in.capacidad_pasajeros,
        anio_fabricacion=vehiculo_in.anio_fabricacion,
        estado=vehiculo_in.estado,
        ubicacion_actual=vehiculo_in.ubicacion_actual
    )
    return updated

@router.get("/conductores", response_model=List[ConductorOut], summary="Listar conductores habilitados")
def listar_conductores(
    ciudad: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(get_current_user)
):
    repo = UsuarioRepository(db)
    if ciudad:
        return repo.list_conductores_by_ubicacion(ciudad)
    return repo.list_conductores()
