from uuid import UUID
from typing import List, Optional
from sqlalchemy.orm import Session, joinedload
from app.models.models import CamaraVehiculo, Vehiculo

class CamaraRepository:
    def __init__(self, db: Session):
        self.db = db

    def list_all(self) -> List[CamaraVehiculo]:
        return (
            self.db.query(CamaraVehiculo)
            .options(joinedload(CamaraVehiculo.vehiculo))
            .order_by(CamaraVehiculo.codigo_camara.asc())
            .all()
        )

    def get_by_id(self, camara_id: UUID) -> Optional[CamaraVehiculo]:
        return (
            self.db.query(CamaraVehiculo)
            .options(joinedload(CamaraVehiculo.vehiculo))
            .filter(CamaraVehiculo.id == camara_id)
            .first()
        )

    def get_by_codigo(self, codigo: str) -> Optional[CamaraVehiculo]:
        return self.db.query(CamaraVehiculo).filter(CamaraVehiculo.codigo_camara == codigo.strip().upper()).first()

    def get_by_vehiculo_id(self, vehiculo_id: UUID) -> Optional[CamaraVehiculo]:
        return self.db.query(CamaraVehiculo).filter(CamaraVehiculo.vehiculo_id == vehiculo_id).first()

    def get_vehiculos_disponibles_para_camara(self, camara_actual_id: Optional[UUID] = None) -> List[Vehiculo]:
        """
        Retorna vehículos que no tienen cámara asignada, o el vehículo actualmente asignado a esta cámara.
        """
        subquery = self.db.query(CamaraVehiculo.vehiculo_id)
        if camara_actual_id:
            subquery = subquery.filter(CamaraVehiculo.id != camara_actual_id)
        return self.db.query(Vehiculo).filter(~Vehiculo.id.in_(subquery)).order_by(Vehiculo.numero_interno.asc()).all()

    def create(
        self,
        vehiculo_id: UUID,
        codigo_camara: str,
        marca_modelo: Optional[str] = "Cámara Celular Cabina",
        tipo_dispositivo: Optional[str] = "CELULAR_CONDUCTOR",
        resolucion: Optional[str] = "640x480",
        estado: Optional[str] = "ACTIVA"
    ) -> CamaraVehiculo:
        camara = CamaraVehiculo(
            vehiculo_id=vehiculo_id,
            codigo_camara=codigo_camara.strip().upper(),
            marca_modelo=marca_modelo.strip() if marca_modelo else "Cámara Celular Cabina",
            tipo_dispositivo=tipo_dispositivo or "CELULAR_CONDUCTOR",
            resolucion=resolucion or "640x480",
            estado=estado or "ACTIVA"
        )
        self.db.add(camara)
        self.db.commit()
        self.db.refresh(camara)
        return camara

    def update(
        self,
        camara_id: UUID,
        vehiculo_id: UUID,
        codigo_camara: str,
        marca_modelo: Optional[str],
        tipo_dispositivo: Optional[str],
        resolucion: Optional[str],
        estado: Optional[str]
    ) -> Optional[CamaraVehiculo]:
        camara = self.get_by_id(camara_id)
        if not camara:
            return None
        camara.vehiculo_id = vehiculo_id
        camara.codigo_camara = codigo_camara.strip().upper()
        if marca_modelo is not None:
            camara.marca_modelo = marca_modelo.strip()
        if tipo_dispositivo is not None:
            camara.tipo_dispositivo = tipo_dispositivo
        if resolucion is not None:
            camara.resolucion = resolucion
        if estado is not None:
            camara.estado = estado
        self.db.commit()
        self.db.refresh(camara)
        return camara

    def delete(self, camara_id: UUID) -> bool:
        camara = self.get_by_id(camara_id)
        if not camara:
            return False
        self.db.delete(camara)
        self.db.commit()
        return True

