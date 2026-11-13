import uuid
import enum
from datetime import datetime, date
from sqlalchemy import (
    Column, String, Boolean, Numeric, Integer, Float,
    DateTime, Date, ForeignKey, Enum as SQLEnum, Text, UniqueConstraint, JSON
)
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship
from app.core.database import Base

# =========================================================
# ENUMS PARA RESTRICCIONES DE DOMINIO
# =========================================================

class RolUsuario(str, enum.Enum):
    ADMIN = "ADMIN"
    OPERADOR = "OPERADOR"
    CONDUCTOR = "CONDUCTOR"

class EstadoVehiculo(str, enum.Enum):
    DISPONIBLE = "DISPONIBLE"
    EN_TRANSITO = "EN_TRANSITO"
    MANTENIMIENTO = "MANTENIMIENTO"

class TipoBus(str, enum.Enum):
    CAMA = "CAMA"
    SEMI_CAMA = "SEMI_CAMA"
    NORMAL = "NORMAL"
    LEITO = "LEITO"

class EstadoHoja(str, enum.Enum):
    BORRADOR = "BORRADOR"
    PRE_DESPACHO = "PRE_DESPACHO"
    AUTORIZADA = "AUTORIZADA"
    EN_TRANSITO = "EN_TRANSITO"
    FINALIZADA = "FINALIZADA"
    CANCELADA = "CANCELADA"

class TipoConductor(str, enum.Enum):
    PRINCIPAL = "PRINCIPAL"
    RELEVO = "RELEVO"

class TipoIncidente(str, enum.Enum):
    FATIGA_CRITICA = "FATIGA_CRITICA"
    SOMNOLENCIA_PREVENTIVA = "SOMNOLENCIA_PREVENTIVA"
    EXCESO_VELOCIDAD = "EXCESO_VELOCIDAD"

class NivelRiesgo(str, enum.Enum):
    VERDE = "VERDE"
    AMARILLO = "AMARILLO"
    ROJO = "ROJO"

class AccionAtencion(str, enum.Enum):
    LLAMADA_VERIFICACION = "LLAMADA_VERIFICACION"
    ORDEN_DESCANSO = "ORDEN_DESCANSO"
    SOLICITUD_RELEVO = "SOLICITUD_RELEVO"
    FALSA_ALARMA = "FALSA_ALARMA"


# =========================================================
# MODELOS ORM (ENTIDADES)
# =========================================================

class Rol(Base):
    __tablename__ = "rol"

    id = Column(Integer, primary_key=True, autoincrement=True)
    nombre = Column(String(50), unique=True, nullable=False)
    descripcion = Column(Text, nullable=True)
    
    # Relaciones
    usuarios = relationship("Usuario", back_populates="rol_info")


class Usuario(Base):
    __tablename__ = "usuario"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    ci = Column(String(20), unique=True, nullable=False, index=True)
    nombre = Column(String(100), nullable=False)
    apellido = Column(String(100), nullable=False)
    email = Column(String(150), unique=True, nullable=False, index=True)
    password_hash = Column(String(255), nullable=False)
    rol_id = Column(Integer, ForeignKey("rol.id"), nullable=False)
    telefono = Column(String(20), nullable=True)
    tipo_sangre = Column(String(10), nullable=True)
    departamento = Column(String(50), nullable=True)
    terminal_asignada = Column(String(100), nullable=True)
    foto_url = Column(String(255), nullable=True)
    estado = Column(Boolean, default=True, nullable=False)
    fecha_creacion = Column(DateTime(timezone=True), default=datetime.utcnow)

    # Relaciones
    rol_info = relationship("Rol", back_populates="usuarios")
    conductor = relationship("Conductor", back_populates="usuario", uselist=False, cascade="all, delete-orphan")

    @property
    def rol(self):
        class _Rol:
            def __init__(self, value):
                self.value = value
            def __eq__(self, other):
                if hasattr(other, "value"):
                    return self.value == other.value
                return self.value == other
            def __str__(self):
                return self.value
        return _Rol(self.rol_info.nombre if self.rol_info else "CONDUCTOR")

class Conductor(Base):
    __tablename__ = "conductor"

    id = Column(UUID(as_uuid=True), ForeignKey("usuario.id", ondelete="CASCADE"), primary_key=True)
    licencia_conducir = Column(String(30), unique=True, nullable=False)
    categoria_licencia = Column(String(10), nullable=False)
    telefono_emergencia = Column(String(20), nullable=True)
    contacto_emergencia_nombre = Column(String(100), nullable=True)
    puntaje_promedio = Column(Numeric(3, 2), default=0.00)
    viajes_concluidos = Column(Integer, default=0, nullable=False)
    ubicacion_actual = Column(String(100), nullable=True)

    # Relaciones
    usuario = relationship("Usuario", back_populates="conductor")
    asignaciones = relationship("AsignacionTripulacion", back_populates="conductor")


class Vehiculo(Base):
    __tablename__ = "vehiculo"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    placa = Column(String(15), unique=True, nullable=False, index=True)
    numero_interno = Column(String(20), nullable=False)
    marca = Column(String(50), nullable=False)
    modelo = Column(String(50), nullable=False)
    chasis = Column(String(50), nullable=True)
    carroceria = Column(String(50), nullable=True)
    capacidad_pasajeros = Column(Integer, nullable=True)
    tipo_bus = Column(SQLEnum(TipoBus, name="tipo_bus_enum"), default=TipoBus.SEMI_CAMA, nullable=False)
    anio_fabricacion = Column(Integer, nullable=True)
    kilometraje_actual = Column(Numeric(10, 2), default=0.00)
    fecha_ultimo_mantenimiento = Column(Date, nullable=True)
    soat_numero = Column(String(30), nullable=True)
    soat_vigencia = Column(Date, nullable=True)
    estado = Column(SQLEnum(EstadoVehiculo, name="estado_vehiculo_enum"), default=EstadoVehiculo.DISPONIBLE, nullable=False)
    foto_url = Column(String(255), nullable=True)
    ubicacion_actual = Column(String(100), nullable=True)
    terminal_actual = Column(String(100), nullable=True)

    # Relaciones
    hojas_de_ruta = relationship("HojaDeRuta", back_populates="vehiculo")
    camara = relationship("CamaraVehiculo", back_populates="vehiculo", uselist=False, cascade="all, delete-orphan")


class HojaDeRuta(Base):
    __tablename__ = "hoja_de_ruta"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    codigo_hoja = Column(String(30), unique=True, nullable=False, index=True)
    vehiculo_id = Column(UUID(as_uuid=True), ForeignKey("vehiculo.id"), nullable=False)
    origen_ciudad = Column(String(50), nullable=False)
    origen_terminal = Column(String(100), nullable=False)
    destino_ciudad = Column(String(50), nullable=False)
    destino_terminal = Column(String(100), nullable=False)
    terminales_intermedias = Column(JSON().with_variant(JSONB, "postgresql"), nullable=True)
    distancia_km = Column(Numeric(6, 2), nullable=True)
    duracion_estimada_hrs = Column(Numeric(4, 2), nullable=True)
    fecha_salida = Column(DateTime(timezone=True), nullable=False)
    fecha_llegada_estimada = Column(DateTime(timezone=True), nullable=False)
    fecha_inicio_real = Column(DateTime(timezone=True), nullable=True)
    fecha_fin_real = Column(DateTime(timezone=True), nullable=True)
    duracion_real_hrs = Column(Numeric(5, 2), nullable=True)
    estado = Column(SQLEnum(EstadoHoja, name="estado_hoja_enum"), default=EstadoHoja.BORRADOR, nullable=False, index=True)

    # Relaciones
    vehiculo = relationship("Vehiculo", back_populates="hojas_de_ruta")
    tripulacion = relationship("AsignacionTripulacion", back_populates="hoja_de_ruta", cascade="all, delete-orphan")
    pre_despacho = relationship("PreDespacho", back_populates="hoja_de_ruta", uselist=False, cascade="all, delete-orphan")
    telemetrias = relationship("RegistroTelemetria", back_populates="hoja_de_ruta", cascade="all, delete-orphan")
    incidentes = relationship("IncidenteAlerta", back_populates="hoja_de_ruta", cascade="all, delete-orphan")


class AsignacionTripulacion(Base):
    __tablename__ = "asignacion_tripulacion"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    hoja_de_ruta_id = Column(UUID(as_uuid=True), ForeignKey("hoja_de_ruta.id", ondelete="CASCADE"), nullable=False)
    conductor_id = Column(UUID(as_uuid=True), ForeignKey("conductor.id"), nullable=False)
    tipo_conductor = Column(SQLEnum(TipoConductor, name="tipo_conductor_enum"), nullable=False)
    fecha_asignacion = Column(DateTime(timezone=True), default=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint("hoja_de_ruta_id", "conductor_id", name="uk_hoja_conductor"),
    )

    # Relaciones
    hoja_de_ruta = relationship("HojaDeRuta", back_populates="tripulacion")
    conductor = relationship("Conductor", back_populates="asignaciones")


class PreDespacho(Base):
    __tablename__ = "pre_despacho"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    hoja_de_ruta_id = Column(UUID(as_uuid=True), ForeignKey("hoja_de_ruta.id", ondelete="CASCADE"), unique=True, nullable=False)
    operador_terminal_id = Column(UUID(as_uuid=True), ForeignKey("usuario.id"), nullable=False)
    resultado_alcotest = Column(Numeric(3, 2), nullable=False, default=0.00)
    resultado_alcotest_principal = Column(Numeric(3, 2), nullable=True, default=0.00)
    aprobado_principal = Column(Boolean, default=False, nullable=False)
    resultado_alcotest_relevo = Column(Numeric(3, 2), nullable=True)
    aprobado_relevo = Column(Boolean, default=None, nullable=True)
    aprobado = Column(Boolean, default=False, nullable=False)
    observaciones = Column(Text, nullable=True)
    fecha_validacion = Column(DateTime(timezone=True), default=datetime.utcnow)

    # Relaciones
    hoja_de_ruta = relationship("HojaDeRuta", back_populates="pre_despacho")
    operador_terminal = relationship("Usuario")


class RegistroTelemetria(Base):
    __tablename__ = "registro_telemetria"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    hoja_de_ruta_id = Column(UUID(as_uuid=True), ForeignKey("hoja_de_ruta.id", ondelete="CASCADE"), nullable=False)
    conductor_id = Column(UUID(as_uuid=True), ForeignKey("conductor.id"), nullable=False)
    latitud = Column(Float, nullable=False)
    longitud = Column(Float, nullable=False)
    velocidad_kmh = Column(Numeric(5, 2), nullable=False)
    timestamp_captura = Column(DateTime(timezone=True), nullable=False)
    timestamp_sync = Column(DateTime(timezone=True), default=datetime.utcnow)

    # Relaciones
    hoja_de_ruta = relationship("HojaDeRuta", back_populates="telemetrias")
    conductor = relationship("Conductor")


class IncidenteAlerta(Base):
    __tablename__ = "incidente_alerta"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    hoja_de_ruta_id = Column(UUID(as_uuid=True), ForeignKey("hoja_de_ruta.id", ondelete="CASCADE"), nullable=False)
    conductor_id = Column(UUID(as_uuid=True), ForeignKey("conductor.id"), nullable=False)
    tipo_incidente = Column(SQLEnum(TipoIncidente, name="tipo_incidente_enum"), nullable=False)
    indice_fatiga_if = Column(Numeric(3, 2), nullable=True)
    perclos_porcentaje = Column(Numeric(5, 2), nullable=True)
    velocidad_instantanea = Column(Numeric(5, 2), nullable=False)
    latitud = Column(Float, nullable=False)
    longitud = Column(Float, nullable=False)
    nivel_riesgo = Column(SQLEnum(NivelRiesgo, name="nivel_riesgo_enum"), nullable=False)
    alarma_disparada = Column(Boolean, default=False, nullable=False)
    timestamp_evento = Column(DateTime(timezone=True), nullable=False)
    estado_sync = Column(Boolean, default=False, nullable=False)

    # Relaciones
    hoja_de_ruta = relationship("HojaDeRuta", back_populates="incidentes")
    conductor = relationship("Conductor")
    atencion = relationship("AtencionIncidente", back_populates="incidente", uselist=False, cascade="all, delete-orphan")


class AtencionIncidente(Base):
    __tablename__ = "atencion_incidente"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    incidente_id = Column(UUID(as_uuid=True), ForeignKey("incidente_alerta.id", ondelete="CASCADE"), unique=True, nullable=False)
    operador_id = Column(UUID(as_uuid=True), ForeignKey("usuario.id"), nullable=False)
    accion_tomada = Column(SQLEnum(AccionAtencion, name="accion_atencion_enum"), nullable=False)
    mensaje_enviado = Column(Text, nullable=True)
    audio_url = Column(String(255), nullable=True)
    fecha_atencion = Column(DateTime(timezone=True), default=datetime.utcnow)

    # Relaciones
    incidente = relationship("IncidenteAlerta", back_populates="atencion")
    operador = relationship("Usuario")


class CamaraVehiculo(Base):
    __tablename__ = "camara_vehiculo"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    vehiculo_id = Column(UUID(as_uuid=True), ForeignKey("vehiculo.id", ondelete="CASCADE"), unique=True, nullable=False)
    codigo_camara = Column(String(50), unique=True, nullable=False, index=True)
    marca_modelo = Column(String(100), default="Cámara Celular Cabina", nullable=True)
    tipo_dispositivo = Column(String(50), default="CELULAR_CONDUCTOR", nullable=False)
    resolucion = Column(String(20), default="640x480", nullable=True)
    estado = Column(String(20), default="ACTIVA", nullable=False)
    fecha_registro = Column(DateTime(timezone=True), default=datetime.utcnow)

    # Relaciones
    vehiculo = relationship("Vehiculo", back_populates="camara")

