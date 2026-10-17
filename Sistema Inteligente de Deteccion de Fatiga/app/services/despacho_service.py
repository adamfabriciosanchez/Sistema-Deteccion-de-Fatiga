from uuid import UUID
from typing import Optional, List
from fastapi import HTTPException, status
from sqlalchemy.orm import Session
from app.repositories.despacho_repo import DespachoRepository
from app.repositories.flota_repo import VehiculoRepository
from app.repositories.usuario_repo import UsuarioRepository
from app.models.models import (
    HojaDeRuta,
    PreDespacho,
    EstadoHoja,
    EstadoVehiculo,
    TipoConductor,
    Usuario
)
from app.schemas.despacho_schema import HojaDeRutaCreate, PreDespachoCreate

class DespachoService:
    def __init__(self, db: Session):
        self.db = db
        self.repo = DespachoRepository(db)
        self.flota_repo = VehiculoRepository(db)
        self.usuario_repo = UsuarioRepository(db)

    def programar_hoja_de_ruta(self, hoja_in: HojaDeRutaCreate) -> HojaDeRuta:
        """
        Programa una nueva Hoja de Ruta aplicando:
        1. Código único.
        2. Estado del vehículo disponible y sin viaje activo en paralelo.
        3. Conductores sin viaje activo en paralelo.
        4. Regla Crítica ATT de Tripulación Doble:
           - Si duracion_estimada_hrs > 4.0: Exige obligatoriamente 2 conductores (PRINCIPAL y RELEVO).
           - Si duracion_estimada_hrs <= 4.0: Basta con 1 conductor PRINCIPAL.
        """
        # 1. Validar que no exista otra hoja con el mismo código
        existente = self.repo.get_hoja_by_codigo(hoja_in.codigo_hoja)
        if existente:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Ya existe una Hoja de Ruta con el código '{hoja_in.codigo_hoja}'."
            )

        # 2. Validar existencia del vehículo y disponibilidad
        vehiculo = self.flota_repo.get_by_id(hoja_in.vehiculo_id)
        if not vehiculo:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"El vehículo con ID {hoja_in.vehiculo_id} no existe."
            )
        if vehiculo.estado != EstadoVehiculo.DISPONIBLE:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"El bus placa {vehiculo.placa} (Interno #{vehiculo.numero_interno}) no está DISPONIBLE (Estado: {vehiculo.estado.value})."
            )

        if self.repo.is_vehiculo_en_viaje_activo(vehiculo.id):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"El bus placa {vehiculo.placa} ya tiene una hoja de ruta activa asignada."
            )

        # 3. Validar conductores únicos y disponibles
        tipos_asignados = [t.tipo_conductor for t in hoja_in.tripulantes]
        choferes_ids = [t.conductor_id for t in hoja_in.tripulantes]

        if len(choferes_ids) != len(set(choferes_ids)):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="No se puede asignar al mismo conductor dos veces en la misma hoja de ruta."
            )

        for c_id in choferes_ids:
            if self.repo.is_conductor_en_viaje_activo(c_id):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"El conductor con ID {c_id} ya se encuentra asignado a un viaje en curso."
                )

        # Verificar que debe existir al menos un conductor PRINCIPAL
        if TipoConductor.PRINCIPAL not in tipos_asignados:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Toda hoja de ruta debe contar obligatoriamente con un conductor PRINCIPAL."
            )

        # =========================================================
        # [EVENTO 1: VERIFICACIÓN DE REGLA ATT DE TRIPULACIÓN DOBLE]
        # Si la duración estimada supera 4.0 horas, exige conductor de RELEVO
        # =========================================================
        duracion_hrs = float(hoja_in.duracion_estimada_hrs) if hoja_in.duracion_estimada_hrs else 0.0
        if duracion_hrs > 4.0:
            if TipoConductor.RELEVO not in tipos_asignados or len(hoja_in.tripulantes) < 2:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=(
                        f"Regla ATT Incumplida: La ruta {hoja_in.origen_ciudad} -> {hoja_in.destino_ciudad} tiene una duración "
                        f"estimada de {duracion_hrs} horas (> 4.0 hrs). Es obligatoria la asignación de "
                        f"TRIPULACIÓN DOBLE (un conductor PRINCIPAL y un conductor de RELEVO)."
                    )
                )

        # 5. Crear la Hoja de Ruta
        return self.repo.create_hoja(hoja_in)

    def registrar_pre_despacho(
        self,
        pre_in: PreDespachoCreate,
        operador_actual: Usuario
    ) -> PreDespacho:
        """
        Registra el resultado de la prueba de Alcotest en Terminal para la tripulación:
        - Si hay 2 conductores: Exige alcotest individual para Principal y Relevo.
          Ambos deben registrar 0.00 mg/L para que la hoja pase a AUTORIZADA.
        - Si 1 reprueba (> 0.00 mg/L): La hoja queda en PRE_DESPACHO para permitir
          al Jefe de Operaciones reasignar al conductor reprobado.
        """
        hoja = self.repo.get_hoja_by_id(pre_in.hoja_de_ruta_id)
        if not hoja:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"La hoja de ruta con ID {pre_in.hoja_de_ruta_id} no existe."
            )

        if hoja.estado not in [EstadoHoja.PRE_DESPACHO, EstadoHoja.BORRADOR]:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"La hoja de ruta ya no se encuentra en estado de Pre-Despacho (Estado actual: {hoja.estado.value})."
            )

        tiene_relevo = any(t.tipo_conductor == TipoConductor.RELEVO for t in hoja.tripulacion)

        # Determinar valores de alcotest
        alcotest_p = pre_in.resultado_alcotest_principal if pre_in.resultado_alcotest_principal is not None else pre_in.resultado_alcotest
        aprobado_p = (float(alcotest_p) == 0.00)

        if tiene_relevo:
            alcotest_r = pre_in.resultado_alcotest_relevo if pre_in.resultado_alcotest_relevo is not None else pre_in.resultado_alcotest
            aprobado_r = (float(alcotest_r) == 0.00)
            es_aprobado = aprobado_p and aprobado_r
            alcotest_general = max(float(alcotest_p), float(alcotest_r))
        else:
            alcotest_r = None
            aprobado_r = None
            es_aprobado = aprobado_p
            alcotest_general = float(alcotest_p)

        # Guardar registro
        # =========================================================
        # [EVENTO 2: REGISTRO DE ALCOTEST EN TERMINAL]
        # =========================================================
        pre_despacho = self.repo.create_pre_despacho(
            hoja_id=hoja.id,
            operador_id=operador_actual.id,
            alcotest=alcotest_general,
            aprobado=es_aprobado,
            observaciones=pre_in.observaciones,
            alcotest_principal=float(alcotest_p),
            aprobado_principal=aprobado_p,
            alcotest_relevo=float(alcotest_r) if alcotest_r is not None else None,
            aprobado_relevo=aprobado_r
        )

        # =========================================================
        # [EVENTO 3: APROBACIÓN DE PRE-DESPACHO Y EMISIÓN WEBSOCKET]
        # Si aprueba (0.00 mg/L), la hoja pasa a AUTORIZADA y emite pin gris en terminal
        # =========================================================
        if es_aprobado:
            self.repo.update_estado(hoja.id, EstadoHoja.AUTORIZADA)
            try:
                import asyncio
                from app.services.rutas_oficiales import get_coordenadas_ciudad
                lat, lng = get_coordenadas_ciudad(hoja.origen_ciudad)
                chofer_txt = "Conductor Asignado"
                for t in hoja.tripulacion:
                    if t.rol_conductor.value == "PRINCIPAL" and t.conductor and t.conductor.usuario:
                        chofer_txt = f"{t.conductor.usuario.nombre} {t.conductor.usuario.apellido}"
                        break
                data_bus = {
                    "hoja_de_ruta_id": str(hoja.id),
                    "codigo_hoja": hoja.codigo_hoja,
                    "bus_numero_interno": hoja.vehiculo.numero_interno if hoja.vehiculo else "--",
                    "bus_disco": hoja.vehiculo.numero_interno if hoja.vehiculo else "--",
                    "bus_placa": hoja.vehiculo.placa if hoja.vehiculo else "--",
                    "bus_modelo": hoja.vehiculo.modelo if hoja.vehiculo else "--",
                    "ruta": f"{hoja.origen_ciudad} -> {hoja.destino_ciudad}",
                    "conductor": chofer_txt,
                    "latitud": lat,
                    "longitud": lng,
                    "velocidad_kmh": 0.0,
                    "nivel_riesgo": "GRIS",
                    "estado_hoja": "AUTORIZADA",
                    "alerta_mensaje": None,
                    "timestamp": datetime.utcnow().isoformat()
                }
                asyncio.create_task(manager.broadcast_to_dashboard({
                    "tipo_evento": "HOJA_AUTORIZADA",
                    "data": data_bus
                }))
            except Exception:
                pass

        return pre_despacho

    def reasignar_conductor(
        self,
        hoja_id: UUID,
        tipo_conductor: TipoConductor,
        nuevo_conductor_id: UUID
    ) -> HojaDeRuta:
        """
        [EVENTO 4: REASIGNACIÓN DE CONDUCTOR POR ALCOTEST POSITIVO]
        Permite al Jefe de Operaciones reemplazar al chofer que reprobó,
        exclusivamente mientras la hoja esté en estado PRE_DESPACHO.
        """
        hoja = self.repo.get_hoja_by_id(hoja_id)
        if not hoja:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Hoja de ruta no encontrada.")

        if hoja.estado != EstadoHoja.PRE_DESPACHO:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Solo se puede reasignar tripulación mientras la hoja esté en PRE_DESPACHO (Estado actual: {hoja.estado.value})."
            )

        # Validar nuevo conductor
        nuevo_cond = self.usuario_repo.get_conductor_by_id(nuevo_conductor_id)
        if not nuevo_cond:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="El nuevo conductor no existe.")

        # Validar colisión en viaje activo
        if self.repo.is_conductor_en_viaje_activo(nuevo_conductor_id):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"El nuevo conductor ya se encuentra asignado a un viaje en curso."
            )

        # Validar ciudad de origen vs base actual del nuevo conductor
        if nuevo_cond.ubicacion_actual and nuevo_cond.ubicacion_actual.strip().lower() != hoja.origen_ciudad.strip().lower():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"El nuevo conductor está en {nuevo_cond.ubicacion_actual}, pero el viaje sale de {hoja.origen_ciudad}."
            )

        hoja_actualizada = self.repo.reasignar_conductor(hoja_id, tipo_conductor, nuevo_conductor_id)
        if not hoja_actualizada:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No se pudo reasignar el conductor.")

        return hoja_actualizada

    def autorizar_salida_transito(self, hoja_id: UUID) -> HojaDeRuta:
        """
        [EVENTO 5: INICIO DE TRÁNSITO EN CARRETERA]
        Pasa la hoja a EN_TRANSITO y emite el evento VIAJE_INICIADO por WebSocket
        (en el mapa el pin del bus cambia inmediatamente de gris a verde).
        """
        hoja = self.repo.get_hoja_by_id(hoja_id)
        if not hoja:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Hoja de ruta no encontrada.")

        if hoja.estado != EstadoHoja.AUTORIZADA:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"No se puede iniciar tránsito: La hoja de ruta debe estar AUTORIZADA (Estado actual: {hoja.estado.value})."
            )

        self.repo.update_estado(hoja.id, EstadoHoja.EN_TRANSITO)
        self.flota_repo.update_estado(hoja.vehiculo_id, EstadoVehiculo.EN_TRANSITO)
        try:
            import asyncio
            asyncio.create_task(manager.broadcast_to_dashboard({
                "tipo_evento": "VIAJE_INICIADO",
                "hoja_de_ruta_id": str(hoja.id)
            }))
        except Exception:
            pass
        return self.repo.get_hoja_by_id(hoja_id)

    def finalizar_viaje(self, hoja_id: UUID) -> HojaDeRuta:
        """
        [EVENTO 6: FINALIZACIÓN DE VIAJE, CÁLCULO DE TIEMPO REAL Y RETORNO A BASE]
        Pasa la hoja a FINALIZADA, calcula la duracion_real_hrs, libera el bus a DISPONIBLE,
        emite evento VIAJE_FINALIZADO y reasigna la base geográfica de bus y choferes al destino.
        """
        hoja = self.repo.get_hoja_by_id(hoja_id)
        if not hoja:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Hoja de ruta no encontrada.")

        if hoja.estado != EstadoHoja.EN_TRANSITO:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Solo se pueden finalizar viajes que estén EN TRÁNSITO (Estado actual: {hoja.estado.value})."
            )

        self.repo.update_estado(hoja.id, EstadoHoja.FINALIZADA)
        self.flota_repo.update_estado(hoja.vehiculo_id, EstadoVehiculo.DISPONIBLE)

        # Actualizar ubicación de llegada del bus y choferes
        self.flota_repo.update_ubicacion(hoja.vehiculo_id, hoja.destino_ciudad)
        for t in hoja.tripulacion:
            self.usuario_repo.update_conductor_ubicacion(t.conductor_id, hoja.destino_ciudad)

        try:
            import asyncio
            asyncio.create_task(manager.broadcast_to_dashboard({
                "tipo_evento": "VIAJE_FINALIZADO",
                "hoja_de_ruta_id": str(hoja.id)
            }))
        except Exception:
            pass

        return self.repo.get_hoja_by_id(hoja_id)
