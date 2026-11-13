from uuid import UUID
from typing import List, Optional
from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.core.dependencies import get_current_user, require_roles
from app.models.models import RolUsuario, Usuario, EstadoHoja
from app.schemas.despacho_schema import (
    HojaDeRutaCreate,
    HojaDeRutaOut,
    PreDespachoCreate,
    PreDespachoOut,
    HojaDeRutaReasignarConductor
)
from app.services.despacho_service import DespachoService
from app.services.rutas_oficiales import calcular_ruta_oficial, get_terminales_ciudad
from app.repositories.despacho_repo import DespachoRepository

router = APIRouter(tags=["Hojas de Ruta y Despacho"])

@router.get("/rutas-oficiales/calcular", summary="Calcular distancia y duración oficial entre ciudades")
def api_calcular_ruta(origen: str, destino: str):
    return calcular_ruta_oficial(origen, destino)

@router.get("/rutas-oficiales/terminales/{ciudad}", summary="Obtener terminales disponibles en una ciudad")
def api_obtener_terminales(ciudad: str):
    return {"ciudad": ciudad, "terminales": get_terminales_ciudad(ciudad)}

@router.get("/hojas-de-ruta", response_model=List[HojaDeRutaOut], summary="Listar hojas de ruta")
def listar_hojas_de_ruta(
    estado: Optional[EstadoHoja] = None,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(get_current_user)
):
    repo = DespachoRepository(db)
    if current_user.rol == RolUsuario.CONDUCTOR:
        return repo.list_hojas_by_conductor(current_user.id)
    return repo.list_hojas(estado=estado)

@router.get("/hojas-de-ruta/{hoja_id}", response_model=HojaDeRutaOut, summary="Obtener detalle de hoja de ruta")
def obtener_hoja_de_ruta(
    hoja_id: UUID,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(get_current_user)
):
    repo = DespachoRepository(db)
    return repo.get_hoja_by_id(hoja_id)

@router.post("/hojas-de-ruta", response_model=HojaDeRutaOut, status_code=status.HTTP_201_CREATED, summary="Programar nueva hoja de ruta con validación ATT (Admin)")
def programar_hoja(
    hoja_in: HojaDeRutaCreate,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_roles([RolUsuario.ADMIN]))
):
    service = DespachoService(db)
    return service.programar_hoja_de_ruta(hoja_in)

@router.post("/hojas-de-ruta/{hoja_id}/reasignar-conductor", response_model=HojaDeRutaOut, summary="Reasignar conductor reprobado en pre-despacho (Admin)")
def api_reasignar_conductor(
    hoja_id: UUID,
    datos: HojaDeRutaReasignarConductor,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_roles([RolUsuario.ADMIN]))
):
    service = DespachoService(db)
    return service.reasignar_conductor(hoja_id, datos.tipo_conductor, datos.nuevo_conductor_id)

@router.post("/pre-despacho", response_model=PreDespachoOut, status_code=status.HTTP_201_CREATED, summary="Registrar validación de alcotest (Exclusivo Jefe de Operaciones - Admin)")
def registrar_pre_despacho(
    pre_in: PreDespachoCreate,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_roles([RolUsuario.ADMIN]))
):
    service = DespachoService(db)
    return service.registrar_pre_despacho(pre_in, operador_actual=current_user)

@router.post("/hojas-de-ruta/{hoja_id}/iniciar-transito", response_model=HojaDeRutaOut, summary="Iniciar tránsito de bus autorizado")
def iniciar_transito(
    hoja_id: UUID,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_roles([RolUsuario.ADMIN, RolUsuario.OPERADOR, RolUsuario.CONDUCTOR]))
):
    service = DespachoService(db)
    return service.autorizar_salida_transito(hoja_id)

@router.post("/hojas-de-ruta/{hoja_id}/finalizar", response_model=HojaDeRutaOut, summary="Finalizar viaje y liberar bus a Disponible")
def finalizar_viaje(
    hoja_id: UUID,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_roles([RolUsuario.ADMIN, RolUsuario.OPERADOR, RolUsuario.CONDUCTOR]))
):
    service = DespachoService(db)
    return service.finalizar_viaje(hoja_id)

@router.post("/reasignar-conductor", response_model=HojaDeRutaOut, summary="Reasignar conductor en estado PRE_DESPACHO")
def api_reasignar_conductor(
    data: HojaDeRutaReasignarConductor,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_roles([RolUsuario.ADMIN]))
):
    service = DespachoService(db)
    return service.reasignar_conductor(
        hoja_id=data.hoja_de_ruta_id,
        tipo_conductor=data.tipo_conductor,
        nuevo_conductor_id=data.nuevo_conductor_id
    )
