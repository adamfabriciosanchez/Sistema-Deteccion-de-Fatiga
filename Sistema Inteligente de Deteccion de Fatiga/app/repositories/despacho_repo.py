from typing import Optional, List
from uuid import UUID
from datetime import datetime, date
from sqlalchemy.orm import Session, joinedload
from app.models.models import (
    HojaDeRuta,
    AsignacionTripulacion,
    PreDespacho,
    EstadoHoja,
    Vehiculo,
    Conductor,
    Usuario,
    TipoConductor
)
from app.schemas.despacho_schema import HojaDeRutaCreate, PreDespachoCreate

class DespachoRepository:
    def __init__(self, db: Session):
        self.db = db

    def get_hoja_by_id(self, hoja_id: UUID) -> Optional[HojaDeRuta]:
        return (
            self.db.query(HojaDeRuta)
            .options(
                joinedload(HojaDeRuta.vehiculo),
                joinedload(HojaDeRuta.pre_despacho).joinedload(PreDespacho.operador_terminal),
                joinedload(HojaDeRuta.tripulacion).joinedload(AsignacionTripulacion.conductor).joinedload(Conductor.usuario)
            )
            .filter(HojaDeRuta.id == hoja_id)
            .first()
        )

    def get_hoja_by_codigo(self, codigo_hoja: str) -> Optional[HojaDeRuta]:
        return (
            self.db.query(HojaDeRuta)
            .filter(HojaDeRuta.codigo_hoja == codigo_hoja.strip().upper())
            .first()
        )

    def list_hojas(
        self,
        estado: Optional[EstadoHoja] = None,
        fecha: Optional[date] = None,
        busqueda: Optional[str] = None
    ) -> List[HojaDeRuta]:
        query = (
            self.db.query(HojaDeRuta)
            .options(
                joinedload(HojaDeRuta.vehiculo),
                joinedload(HojaDeRuta.pre_despacho).joinedload(PreDespacho.operador_terminal),
                joinedload(HojaDeRuta.tripulacion).joinedload(AsignacionTripulacion.conductor).joinedload(Conductor.usuario)
            )
            .order_by(HojaDeRuta.fecha_salida.desc())
        )
        if estado:
            query = query.filter(HojaDeRuta.estado == estado)
        if fecha:
            query = query.filter(
                HojaDeRuta.fecha_salida >= datetime.combine(fecha, datetime.min.time()),
                HojaDeRuta.fecha_salida <= datetime.combine(fecha, datetime.max.time())
            )
        if busqueda:
            term = f"%{busqueda.strip()}%"
            query = query.filter(
                (HojaDeRuta.codigo_hoja.ilike(term)) |
                (HojaDeRuta.origen_ciudad.ilike(term)) |
                (HojaDeRuta.destino_ciudad.ilike(term))
            )
        return query.all()

    def list_hojas_by_conductor(self, conductor_id: UUID) -> List[HojaDeRuta]:
        return (
            self.db.query(HojaDeRuta)
            .join(AsignacionTripulacion, AsignacionTripulacion.hoja_de_ruta_id == HojaDeRuta.id)
            .options(
                joinedload(HojaDeRuta.vehiculo),
                joinedload(HojaDeRuta.pre_despacho).joinedload(PreDespacho.operador_terminal),
                joinedload(HojaDeRuta.tripulacion).joinedload(AsignacionTripulacion.conductor).joinedload(Conductor.usuario)
            )
            .filter(AsignacionTripulacion.conductor_id == conductor_id)
            .order_by(HojaDeRuta.fecha_salida.desc())
            .all()
        )

    def is_vehiculo_en_viaje_activo(self, vehiculo_id: UUID) -> bool:
        """Verifica si el vehículo está asignado a un viaje en curso o pre-despacho."""
        hoja_activa = (
            self.db.query(HojaDeRuta)
            .filter(
                HojaDeRuta.vehiculo_id == vehiculo_id,
                HojaDeRuta.estado.in_([EstadoHoja.PRE_DESPACHO, EstadoHoja.AUTORIZADA, EstadoHoja.EN_TRANSITO])
            )
            .first()
        )
        return hoja_activa is not None

    def is_conductor_en_viaje_activo(self, conductor_id: UUID) -> bool:
        """Verifica si el conductor está asignado a un viaje en curso o pre-despacho."""
        hoja_activa = (
            self.db.query(HojaDeRuta)
            .join(AsignacionTripulacion, AsignacionTripulacion.hoja_de_ruta_id == HojaDeRuta.id)
            .filter(
                AsignacionTripulacion.conductor_id == conductor_id,
                HojaDeRuta.estado.in_([EstadoHoja.PRE_DESPACHO, EstadoHoja.AUTORIZADA, EstadoHoja.EN_TRANSITO])
            )
            .first()
        )
        return hoja_activa is not None

    def create_hoja(self, hoja_in: HojaDeRutaCreate) -> HojaDeRuta:
        db_hoja = HojaDeRuta(
            codigo_hoja=hoja_in.codigo_hoja.strip().upper(),
            vehiculo_id=hoja_in.vehiculo_id,
            origen_ciudad=hoja_in.origen_ciudad.strip(),
            origen_terminal=hoja_in.origen_terminal.strip(),
            destino_ciudad=hoja_in.destino_ciudad.strip(),
            destino_terminal=hoja_in.destino_terminal.strip(),
            terminales_intermedias=hoja_in.terminales_intermedias,
            distancia_km=hoja_in.distancia_km,
            duracion_estimada_hrs=hoja_in.duracion_estimada_hrs,
            fecha_salida=hoja_in.fecha_salida,
            fecha_llegada_estimada=hoja_in.fecha_llegada_estimada,
            estado=EstadoHoja.PRE_DESPACHO  # Lista para la estación de alcotest en terminal
        )
        self.db.add(db_hoja)
        self.db.flush()

        for item in hoja_in.tripulantes:
            asignacion = AsignacionTripulacion(
                hoja_de_ruta_id=db_hoja.id,
                conductor_id=item.conductor_id,
                tipo_conductor=item.tipo_conductor
            )
            self.db.add(asignacion)

        self.db.commit()
        return self.get_hoja_by_id(db_hoja.id)

    def update_estado(self, hoja_id: UUID, nuevo_estado: EstadoHoja) -> Optional[HojaDeRuta]:
        hoja = self.db.query(HojaDeRuta).filter(HojaDeRuta.id == hoja_id).first()
        if hoja:
            hoja.estado = nuevo_estado
            ahora = datetime.utcnow()
            if nuevo_estado == EstadoHoja.EN_TRANSITO and not hoja.fecha_inicio_real:
                hoja.fecha_inicio_real = ahora
            elif nuevo_estado == EstadoHoja.FINALIZADA:
                if not hoja.fecha_fin_real:
                    hoja.fecha_fin_real = ahora
                if hoja.fecha_inicio_real and hoja.fecha_fin_real:
                    t_ini = hoja.fecha_inicio_real.replace(tzinfo=None) if hoja.fecha_inicio_real.tzinfo else hoja.fecha_inicio_real
                    t_fin = hoja.fecha_fin_real.replace(tzinfo=None) if hoja.fecha_fin_real.tzinfo else hoja.fecha_fin_real
                    delta_seg = (t_fin - t_ini).total_seconds()
                    hoja.duracion_real_hrs = round(max(delta_seg, 0.0) / 3600.0, 2)
            self.db.commit()
            return self.get_hoja_by_id(hoja_id)
        return None

    def create_pre_despacho(
        self,
        hoja_id: UUID,
        operador_id: UUID,
        alcotest: float,
        aprobado: bool,
        observaciones: Optional[str] = None,
        alcotest_principal: Optional[float] = None,
        aprobado_principal: Optional[bool] = None,
        alcotest_relevo: Optional[float] = None,
        aprobado_relevo: Optional[bool] = None
    ) -> PreDespacho:
        pre = self.db.query(PreDespacho).filter(PreDespacho.hoja_de_ruta_id == hoja_id).first()
        if pre:
            pre.operador_terminal_id = operador_id
            pre.resultado_alcotest = alcotest
            pre.resultado_alcotest_principal = alcotest_principal if alcotest_principal is not None else alcotest
            pre.aprobado_principal = aprobado_principal if aprobado_principal is not None else aprobado
            pre.resultado_alcotest_relevo = alcotest_relevo
            pre.aprobado_relevo = aprobado_relevo
            pre.aprobado = aprobado
            pre.observaciones = observaciones
            pre.fecha_validacion = datetime.utcnow()
        else:
            pre = PreDespacho(
                hoja_de_ruta_id=hoja_id,
                operador_terminal_id=operador_id,
                resultado_alcotest=alcotest,
                resultado_alcotest_principal=alcotest_principal if alcotest_principal is not None else alcotest,
                aprobado_principal=aprobado_principal if aprobado_principal is not None else aprobado,
                resultado_alcotest_relevo=alcotest_relevo,
                aprobado_relevo=aprobado_relevo,
                aprobado=aprobado,
                observaciones=observaciones,
                fecha_validacion=datetime.utcnow()
            )
            self.db.add(pre)
        self.db.commit()
        self.db.refresh(pre)
        return pre

    def reasignar_conductor(
        self,
        hoja_id: UUID,
        tipo_conductor: TipoConductor,
        nuevo_conductor_id: UUID
    ) -> Optional[HojaDeRuta]:
        """
        Reasigna un conductor en una hoja de ruta si está en PRE_DESPACHO (ej. tras reprobar alcotest).
        """
        hoja = self.db.query(HojaDeRuta).filter(HojaDeRuta.id == hoja_id).first()
        if not hoja or hoja.estado != EstadoHoja.PRE_DESPACHO:
            return None

        asignacion = (
            self.db.query(AsignacionTripulacion)
            .filter(
                AsignacionTripulacion.hoja_de_ruta_id == hoja_id,
                AsignacionTripulacion.tipo_conductor == tipo_conductor
            )
            .first()
        )
        if asignacion:
            asignacion.conductor_id = nuevo_conductor_id
            # Si había un pre-despacho registrado, resetear el alcotest de ese tipo de conductor
            if hoja.pre_despacho:
                if tipo_conductor == TipoConductor.PRINCIPAL:
                    hoja.pre_despacho.resultado_alcotest_principal = 0.0
                    hoja.pre_despacho.aprobado_principal = False
                elif tipo_conductor == TipoConductor.RELEVO:
                    hoja.pre_despacho.resultado_alcotest_relevo = 0.0
                    hoja.pre_despacho.aprobado_relevo = False
                hoja.pre_despacho.aprobado = False
            self.db.commit()
            return self.get_hoja_by_id(hoja_id)
        return None
