from typing import Optional, List
from uuid import UUID
from sqlalchemy.orm import Session
from app.models.models import Vehiculo, EstadoVehiculo
from app.schemas.flota_schema import VehiculoCreate

class VehiculoRepository:
    def __init__(self, db: Session):
        self.db = db

    def get_by_id(self, vehiculo_id: UUID) -> Optional[Vehiculo]:
        return self.db.query(Vehiculo).filter(Vehiculo.id == vehiculo_id).first()

    def get_by_placa(self, placa: str) -> Optional[Vehiculo]:
        return self.db.query(Vehiculo).filter(Vehiculo.placa == placa.strip().upper()).first()

    def get_by_numero_interno(self, numero_interno: str) -> Optional[Vehiculo]:
        return self.db.query(Vehiculo).filter(Vehiculo.numero_interno == numero_interno.strip()).first()

    def list_all(self) -> List[Vehiculo]:
        return self.db.query(Vehiculo).order_by(Vehiculo.numero_interno).all()

    def list_disponibles(self) -> List[Vehiculo]:
        return (
            self.db.query(Vehiculo)
            .filter(Vehiculo.estado == EstadoVehiculo.DISPONIBLE)
            .order_by(Vehiculo.numero_interno)
            .all()
        )

    def list_by_ubicacion(self, ciudad: str) -> List[Vehiculo]:
        return (
            self.db.query(Vehiculo)
            .filter(
                Vehiculo.estado == EstadoVehiculo.DISPONIBLE,
                Vehiculo.ubicacion_actual.ilike(ciudad.strip())
            )
            .order_by(Vehiculo.numero_interno)
            .all()
        )

    def create(self, vehiculo_in: VehiculoCreate) -> Vehiculo:
        placa_clean = vehiculo_in.placa.strip().upper()
        existente = self.get_by_placa(placa_clean)
        if existente:
            return existente

        db_vehiculo = Vehiculo(
            placa=placa_clean,
            numero_interno=vehiculo_in.numero_interno.strip(),
            marca=vehiculo_in.marca.strip(),
            modelo=vehiculo_in.modelo.strip(),
            chasis=vehiculo_in.chasis.strip() if vehiculo_in.chasis else None,
            carroceria=vehiculo_in.carroceria.strip() if vehiculo_in.carroceria else None,
            capacidad_pasajeros=vehiculo_in.capacidad_pasajeros,
            tipo_bus=vehiculo_in.tipo_bus,
            anio_fabricacion=vehiculo_in.anio_fabricacion,
            kilometraje_actual=vehiculo_in.kilometraje_actual or 0.0,
            fecha_ultimo_mantenimiento=vehiculo_in.fecha_ultimo_mantenimiento,
            soat_vigencia=vehiculo_in.soat_vigencia,
            estado=vehiculo_in.estado or EstadoVehiculo.DISPONIBLE,
            foto_url=vehiculo_in.foto_url,
            ubicacion_actual=vehiculo_in.ubicacion_actual.strip() if vehiculo_in.ubicacion_actual else "Cochabamba"
        )
        self.db.add(db_vehiculo)
        self.db.commit()
        self.db.refresh(db_vehiculo)
        return db_vehiculo

    def update(self, vehiculo_id: UUID, **kwargs) -> Optional[Vehiculo]:
        vehiculo = self.get_by_id(vehiculo_id)
        if not vehiculo:
            return None
        
        for key, value in kwargs.items():
            if hasattr(vehiculo, key) and value is not None:
                setattr(vehiculo, key, value)

        self.db.commit()
        self.db.refresh(vehiculo)
        return vehiculo

    def update_estado(self, vehiculo_id: UUID, nuevo_estado: EstadoVehiculo) -> Optional[Vehiculo]:
        vehiculo = self.get_by_id(vehiculo_id)
        if vehiculo:
            vehiculo.estado = nuevo_estado
            self.db.commit()
            self.db.refresh(vehiculo)
        return vehiculo

    def update_ubicacion(self, vehiculo_id: UUID, nueva_ubicacion: str) -> Optional[Vehiculo]:
        vehiculo = self.get_by_id(vehiculo_id)
        if vehiculo:
            vehiculo.ubicacion_actual = nueva_ubicacion.strip()
            self.db.commit()
            self.db.refresh(vehiculo)
        return vehiculo
