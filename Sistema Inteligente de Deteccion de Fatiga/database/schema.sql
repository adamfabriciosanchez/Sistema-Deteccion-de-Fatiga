-- ===============================================================================
-- SISTEMA TRANS COPACABANA - ESQUEMA DE BASE DE DATOS OPTIMIZADO V2 (3FN)
-- POSTGRESQL 15+ / 18+ (SOPORTE GEOESPACIAL Y TELEMETRÍA EN TIEMPO REAL)
-- ===============================================================================

-- 1. Extensiones
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

DO $$
BEGIN
    CREATE EXTENSION IF NOT EXISTS "postgis";
EXCEPTION
    WHEN OTHERS THEN
        RAISE NOTICE 'Extension PostGIS no disponible en esta instalacion. Se usaran columnas directas de latitud/longitud.';
END $$;

-- 2. Creación de Tipos ENUM para Restricciones de Dominio
DO $$ BEGIN
    CREATE TYPE estado_vehiculo_enum AS ENUM ('DISPONIBLE', 'EN_TRANSITO', 'MANTENIMIENTO');
EXCEPTION WHEN duplicate_object THEN null; END $$;

DO $$ BEGIN
    CREATE TYPE tipo_bus_enum AS ENUM ('CAMA', 'SEMI_CAMA', 'NORMAL', 'LEITO');
EXCEPTION WHEN duplicate_object THEN null; END $$;

DO $$ BEGIN
    CREATE TYPE estado_hoja_enum AS ENUM ('BORRADOR', 'PRE_DESPACHO', 'AUTORIZADA', 'EN_TRANSITO', 'FINALIZADA', 'CANCELADA');
EXCEPTION WHEN duplicate_object THEN null; END $$;

DO $$ BEGIN
    CREATE TYPE tipo_conductor_enum AS ENUM ('PRINCIPAL', 'RELEVO');
EXCEPTION WHEN duplicate_object THEN null; END $$;

DO $$ BEGIN
    CREATE TYPE tipo_incidente_enum AS ENUM ('FATIGA_CRITICA', 'SOMNOLENCIA_PREVENTIVA', 'EXCESO_VELOCIDAD');
EXCEPTION WHEN duplicate_object THEN null; END $$;

DO $$ BEGIN
    CREATE TYPE nivel_riesgo_enum AS ENUM ('VERDE', 'AMARILLO', 'ROJO');
EXCEPTION WHEN duplicate_object THEN null; END $$;

DO $$ BEGIN
    CREATE TYPE accion_atencion_enum AS ENUM ('LLAMADA_VERIFICACION', 'ORDEN_DESCANSO', 'SOLICITUD_RELEVO', 'FALSA_ALARMA');
EXCEPTION WHEN duplicate_object THEN null; END $$;

-- =========================================================
-- TABLAS PRINCIPALES
-- =========================================================

-- Tabla: ROL (Para administrar roles de forma correcta y escalable)
CREATE TABLE IF NOT EXISTS rol (
    id SERIAL PRIMARY KEY,
    nombre VARCHAR(50) NOT NULL UNIQUE,
    descripcion TEXT
);

-- Tabla: USUARIO (Supertipo)
CREATE TABLE IF NOT EXISTS usuario (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    ci VARCHAR(20) NOT NULL UNIQUE,
    nombre VARCHAR(100) NOT NULL,
    apellido VARCHAR(100) NOT NULL,
    email VARCHAR(150) NOT NULL UNIQUE,
    password_hash VARCHAR(255) NOT NULL,
    rol_id INTEGER NOT NULL REFERENCES rol(id),
    foto_url VARCHAR(255),
    estado BOOLEAN NOT NULL DEFAULT TRUE,
    fecha_creacion TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Tabla: CONDUCTOR (Subtipo - Hereda de Usuario)
CREATE TABLE IF NOT EXISTS conductor (
    id UUID PRIMARY KEY REFERENCES usuario(id) ON DELETE CASCADE,
    licencia_conducir VARCHAR(30) NOT NULL UNIQUE,
    categoria_licencia VARCHAR(10) NOT NULL,
    telefono_emergencia VARCHAR(20),
    puntaje_promedio NUMERIC(3,2) DEFAULT 5.00 CHECK (puntaje_promedio BETWEEN 0.00 AND 5.00),
    ubicacion_actual VARCHAR(100) -- Departamento/Ciudad donde se encuentra el conductor
);

-- Tabla: VEHICULO (Flota de Buses Trans Copacabana en 1FN)
CREATE TABLE IF NOT EXISTS vehiculo (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    placa VARCHAR(15) NOT NULL UNIQUE,
    numero_interno VARCHAR(20) NOT NULL, -- Reemplaza numero_disco
    marca VARCHAR(50) NOT NULL,
    modelo VARCHAR(50) NOT NULL,
    chasis VARCHAR(50),
    carroceria VARCHAR(50),
    capacidad_pasajeros INTEGER CHECK (capacidad_pasajeros > 0),
    tipo_bus tipo_bus_enum NOT NULL DEFAULT 'SEMI_CAMA',
    anio_fabricacion INTEGER CHECK (anio_fabricacion > 1980),
    kilometraje_actual NUMERIC(10,2) DEFAULT 0.00,
    fecha_ultimo_mantenimiento DATE,
    soat_vigencia DATE,
    estado estado_vehiculo_enum NOT NULL DEFAULT 'DISPONIBLE',
    foto_url VARCHAR(255),
    ubicacion_actual VARCHAR(100) -- Departamento/Ciudad donde se encuentra el bus
);

-- Tabla: HOJA_DE_RUTA (Contiene directamente la información de origen, destino y tiempos)
CREATE TABLE IF NOT EXISTS hoja_de_ruta (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    codigo_hoja VARCHAR(30) NOT NULL UNIQUE,
    vehiculo_id UUID NOT NULL REFERENCES vehiculo(id),
    origen_ciudad VARCHAR(50) NOT NULL,
    origen_terminal VARCHAR(100) NOT NULL,
    destino_ciudad VARCHAR(50) NOT NULL,
    destino_terminal VARCHAR(100) NOT NULL,
    terminales_intermedias JSONB, -- Puntos de paso intermedios opcionales
    distancia_km NUMERIC(6,2) CHECK (distancia_km > 0),
    duracion_estimada_hrs NUMERIC(4,2) CHECK (duracion_estimada_hrs > 0),
    fecha_salida TIMESTAMP WITH TIME ZONE NOT NULL,
    fecha_llegada_estimada TIMESTAMP WITH TIME ZONE NOT NULL,
    fecha_inicio_real TIMESTAMP WITH TIME ZONE, -- Se actualiza cuando el conductor inicia viaje
    fecha_fin_real TIMESTAMP WITH TIME ZONE, -- Se actualiza cuando el conductor finaliza viaje
    duracion_real_hrs NUMERIC(5,2), -- Tiempo real transcurrido entre inicio y finalización
    estado estado_hoja_enum NOT NULL DEFAULT 'BORRADOR'
);

-- Tabla: ASIGNACION_TRIPULACION (Relación N:M Hoja - Conductor con Regla ATT)
CREATE TABLE IF NOT EXISTS asignacion_tripulacion (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    hoja_de_ruta_id UUID NOT NULL REFERENCES hoja_de_ruta(id) ON DELETE CASCADE,
    conductor_id UUID NOT NULL REFERENCES conductor(id),
    tipo_conductor tipo_conductor_enum NOT NULL, -- PRINCIPAL o RELEVO
    fecha_asignacion TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT uk_hoja_conductor UNIQUE (hoja_de_ruta_id, conductor_id)
);

-- Tabla: PRE_DESPACHO (Validación de Terminal - Exclusivamente Alcotest 0.00 mg/L)
CREATE TABLE IF NOT EXISTS pre_despacho (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    hoja_de_ruta_id UUID NOT NULL UNIQUE REFERENCES hoja_de_ruta(id) ON DELETE CASCADE,
    operador_terminal_id UUID NOT NULL REFERENCES usuario(id),
    resultado_alcotest NUMERIC(3,2) NOT NULL DEFAULT 0.00 CHECK (resultado_alcotest >= 0.00),
    resultado_alcotest_principal NUMERIC(3,2) DEFAULT 0.00 CHECK (resultado_alcotest_principal >= 0.00),
    aprobado_principal BOOLEAN DEFAULT FALSE,
    resultado_alcotest_relevo NUMERIC(3,2) DEFAULT NULL,
    aprobado_relevo BOOLEAN DEFAULT NULL,
    aprobado BOOLEAN NOT NULL DEFAULT FALSE,
    observaciones TEXT,
    fecha_validacion TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Tabla: REGISTRO_TELEMETRIA (Posicionamiento GPS y Velocidad en Carretera)
CREATE TABLE IF NOT EXISTS registro_telemetria (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    hoja_de_ruta_id UUID NOT NULL REFERENCES hoja_de_ruta(id) ON DELETE CASCADE,
    conductor_id UUID NOT NULL REFERENCES conductor(id),
    latitud DOUBLE PRECISION NOT NULL,
    longitud DOUBLE PRECISION NOT NULL,
    velocidad_kmh NUMERIC(5,2) NOT NULL CHECK (velocidad_kmh >= 0.00),
    timestamp_captura TIMESTAMP WITH TIME ZONE NOT NULL,
    timestamp_sync TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Tabla: INCIDENTE_ALERTA (Eventos Críticos / Exceso de Velocidad / Fatiga)
CREATE TABLE IF NOT EXISTS incidente_alerta (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    hoja_de_ruta_id UUID NOT NULL REFERENCES hoja_de_ruta(id) ON DELETE CASCADE,
    conductor_id UUID NOT NULL REFERENCES conductor(id),
    tipo_incidente tipo_incidente_enum NOT NULL,
    indice_fatiga_if NUMERIC(3,2) CHECK (indice_fatiga_if BETWEEN 0.00 AND 1.00),
    perclos_porcentaje NUMERIC(5,2) CHECK (perclos_porcentaje BETWEEN 0.00 AND 100.00),
    velocidad_instantanea NUMERIC(5,2) NOT NULL CHECK (velocidad_instantanea >= 0.00),
    latitud DOUBLE PRECISION NOT NULL,
    longitud DOUBLE PRECISION NOT NULL,
    nivel_riesgo nivel_riesgo_enum NOT NULL,
    alarma_disparada BOOLEAN NOT NULL DEFAULT FALSE,
    timestamp_evento TIMESTAMP WITH TIME ZONE NOT NULL,
    estado_sync BOOLEAN NOT NULL DEFAULT FALSE
);

-- Tabla: ATENCION_INCIDENTE (Protocolo de Parada Segura por Operador de Monitoreo)
CREATE TABLE IF NOT EXISTS atencion_incidente (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    incidente_id UUID NOT NULL UNIQUE REFERENCES incidente_alerta(id) ON DELETE CASCADE,
    operador_id UUID NOT NULL REFERENCES usuario(id),
    accion_tomada accion_atencion_enum NOT NULL,
    mensaje_enviado TEXT, -- Mensaje enviado al conductor
    audio_url VARCHAR(255), -- URL del audio enviado al conductor
    fecha_atencion TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- =========================================================
-- ÍNDICES DE RENDIMIENTO
-- =========================================================
CREATE INDEX IF NOT EXISTS idx_telemetria_hoja_fecha ON registro_telemetria (hoja_de_ruta_id, timestamp_captura DESC);
CREATE INDEX IF NOT EXISTS idx_incidente_hoja_fecha ON incidente_alerta (hoja_de_ruta_id, timestamp_evento DESC);
CREATE INDEX IF NOT EXISTS idx_incidente_sync ON incidente_alerta (estado_sync) WHERE estado_sync = FALSE;
CREATE INDEX IF NOT EXISTS idx_hoja_estado ON hoja_de_ruta (estado);
