# Sistema Inteligente de Gestión de Flota y Monitoreo - "Trans Copacabana"
**Módulo 1: Administración y Gestión | Módulo 2: Monitoreo y Centro de Control**
**Arquitectura Limpia 3FN alineada a PostgreSQL y Regulaciones ATT**

---

## 1. Visión General del Proyecto

El sistema **"Trans Copacabana"** es una plataforma web y distribuida diseñada para el control operativo, despacho técnico y monitoreo geoespacial en tiempo real de la flota de buses interdepartamentales de Bolivia.

### Principales Módulos Implementados
1. **Módulo 1: Administración y Gestión**:
   - Autenticación segura mediante tokens **JWT** y cookies HttpOnly.
   - Control de Acceso Basado en Roles (**RBAC**): `ADMIN` (Jefe de Operaciones), `OPERADOR` (Terminal y Monitoreo) y `CONDUCTOR`.
   - Catálogo de Flota de Buses (columnas 1FN: chasis, carrocería, tipo de bus, año de fabricación y **`numero_interno`**).
   - Gestión de Conductores con licencias categoría C, puntaje y ciudad base (`ubicacion_actual`).
   - Programación de Hojas de Ruta dinámicas (1FN sin tabla obsoleta `Ruta`: origen, destino, duración estimada y distancia).
   - **Regla Crítica ATT de Tripulación Doble**: Exigencia obligatoria de dos conductores (un Conductor `PRINCIPAL` y un Conductor de `RELEVO`) para cualquier viaje con duración estimada mayor a 4.0 horas.
   - **Estación de Pre-Despacho (Terminal)**: Validación de salida exclusiva por personal de terminal (Admin/Operador) con control estricto de **Alcotest** (debe registrar $0.00\text{ mg/L}$ para autorizar el viaje).
   - **Bloqueo de Estado en Tránsito**: Las unidades en estado `EN_TRANSITO` no pueden ser alteradas manualmente para prevenir inconsistencias de flota.
   - **Actualización de Ubicación al Finalizar**: Al completar un viaje, la ciudad base del vehículo y los tripulantes se actualiza automáticamente a la `destino_ciudad`.

2. **Módulo 2: Monitoreo y Centro de Control**:
   - Servidor **WebSocket** reactivo para ingesta continua de coordenadas GPS y velocidad desde las unidades en carretera (`/ws/telemetry/{id}`).
   - Canal de difusión en tiempo real hacia la pantalla de los operadores (`/ws/dashboard`).
   - Dashboard interactivo con **Leaflet.js** y OpenStreetMap centrado en el eje vial de Bolivia.
   - Semáforo de riesgo por unidad:
     - **Verde**: Operación regular ($\le 80\text{ km/h}$).
     - **Amarillo**: Advertencia de exceso de velocidad ($> 80\text{ km/h}$).
     - **Rojo**: Parada crítica o emergencia.
   - **Protocolo de Parada Segura (PPS)**: Modal y flujo operativo para el registro de atención ante incidentes en carretera (`accion_tomada`, `mensaje_enviado`, `audio_url`).
   - Alerta audible simulada en cabina del conductor ante instrucciones del operador.
   - Consultas de historial geoespacial en formato estándar **GeoJSON** para repetición o trazado del recorrido.

---

## 2. Arquitectura del Sistema

El proyecto sigue una **Arquitectura por Capas Limpia (Layered Architecture)** para garantizar modularidad, mantenibilidad y desacoplamiento:

```
Sistema Inteligente de Deteccion de Fatiga/
├── app/
│   ├── core/               # Configuración central, conexión a base de datos y seguridad JWT
│   │   ├── config.py
│   │   ├── database.py
│   │   ├── dependencies.py # Inyección de dependencias y validación de RBAC
│   │   └── security.py     # Hashing Bcrypt y codificación JWT
│   ├── models/             # Modelos ORM (SQLAlchemy 2.0) en Tercera Forma Normal (3FN)
│   │   └── models.py
│   ├── schemas/            # Esquemas Pydantic para validación y serialización
│   │   ├── usuario_schema.py
│   │   ├── flota_schema.py
│   │   ├── despacho_schema.py
│   │   └── telemetria_schema.py
│   ├── repositories/       # Capa de Acceso a Datos (Consultas SQL desacopladas)
│   │   ├── usuario_repo.py
│   │   ├── flota_repo.py
│   │   ├── despacho_repo.py
│   │   └── telemetria_repo.py
│   ├── services/           # Lógica de Negocio (Regla ATT, Alcotest, Parada Segura)
│   │   ├── auth_service.py
│   │   ├── despacho_service.py
│   │   └── telemetria_service.py
│   ├── routers/            # Controladores de API REST (/api/v1) y Vistas Web (Jinja2)
│   │   ├── auth_router.py
│   │   ├── flota_router.py
│   │   ├── despacho_router.py
│   │   ├── telemetria_router.py
│   │   └── views_router.py
│   ├── websockets/         # Gestor reactivo de conexiones WebSocket
│   │   └── connection_manager.py
│   ├── static/             # Assets estáticos (CSS corporativo Rojo/Blanco, JS Leaflet)
│   │   ├── css/trans_copacabana.css
│   │   └── js/monitoreo.js
│   └── templates/          # Vistas Jinja2 con Bootstrap 5
│       ├── base.html
│       ├── login.html
│       ├── home.html
│       ├── dashboard.html
│       ├── flota.html
│       ├── usuarios.html
│       ├── hojas_ruta.html
│       ├── pre_despacho.html
│       ├── mi_hoja.html
│       └── monitoreo.html
├── database/               # Scripts DDL y datos semilla
│   ├── schema.sql          # DDL PostgreSQL 3FN canónico
│   └── seed_data.sql       # Datos iniciales para pruebas y puesta en marcha
├── tests/                  # Suite de pruebas automatizadas aisladas e idempotentes
│   ├── test_fase1_db.py
│   ├── test_fase2_auth.py
│   ├── test_fase3_despacho.py
│   ├── test_fase4_websockets.py
│   ├── test_fase5_monitoreo.py
│   └── test_fase6_e2e.py
├── init_db.py              # Inicializador y recreador de base de datos
├── main.py                 # Punto de entrada de la aplicación FastAPI
├── simulador_gps.py        # Simulador de telemetría GPS en carretera
└── requirements.txt        # Dependencias del proyecto
```

---

## 3. Requisitos y Configuración del Entorno

### Requisitos Previos
- **Python 3.11+**
- **PostgreSQL 15+ / 18+** en `localhost:5432` con usuario `postgres` y contraseña `Pulg42,`
- Base de datos: `trans_copacabana_db`

### Instalación de Dependencias
```powershell
pip install -r requirements.txt
```

### Inicialización de Base de Datos
Para recrear la base de datos limpia con su esquema 3FN y datos semilla:
```powershell
python init_db.py
```

---

## 4. Ejecución del Sistema

### 1. Iniciar el Servidor Web (FastAPI)
```powershell
python main.py
```
O con recarga en vivo de desarrollo:
```powershell
uvicorn main:app --reload --host 127.0.0.1 --port 8000
```
- **Portal Web**: [http://localhost:8000](http://localhost:8000)
- **Documentación Swagger API**: [http://localhost:8000/docs](http://localhost:8000/docs)

### 2. Ejecutar el Simulador GPS
En una segunda terminal, corre el simulador para emitir coordenadas en tiempo real hacia el servidor:
```powershell
python simulador_gps.py
```

---

## 5. Cuentas de Acceso Pre-configuradas

Todas las cuentas de prueba tienen la contraseña predeterminada: **`123456`**.

| Rol | Correo Electrónico | Contraseña | Alcance y Vistas |
| :--- | :--- | :--- | :--- |
| **ADMIN** | `admin@transcopacabana.com` | `123456` | Gestión total de flota (`/flota`), personal (`/usuarios`), programación de hojas de ruta (`/hojas-ruta`), pre-despacho y centro de monitoreo. |
| **OPERADOR** | `operador@transcopacabana.com` | `123456` | Estación de Pre-despacho (`/pre-despacho`) con control de alcoholemia, y Centro de Monitoreo en vivo con Leaflet (`/monitoreo`). |
| **CONDUCTOR** | `carlos@conductor.com` | `123456` | Portal personal del chofer (`/mi-hoja`): consulta de viaje asignado, inicio de tránsito, finalización de viaje y recepción de alertas en cabina. |

---

## 6. Ejecución de la Suite de Pruebas Automatizadas

Cada fase del proyecto cuenta con su script de verificación automatizada. Todas las pruebas son independientes e idempotentes:

```powershell
# Fase 1: Conexión y Modelos ORM (3FN)
python tests/test_fase1_db.py

# Fase 2: Autenticación JWT, RBAC y Vistas Base
python tests/test_fase2_auth.py

# Fase 3: Módulo 1 (CRUDs, Regla ATT y Pre-Despacho Alcotest)
python tests/test_fase3_despacho.py

# Fase 4: WebSockets y Telemetría en Tiempo Real
python tests/test_fase4_websockets.py

# Fase 5: Centro de Monitoreo con Leaflet y Parada Segura (PPS)
python tests/test_fase5_monitoreo.py

# Fase 6: Ciclo Completo End-to-End (E2E)
python tests/test_fase6_e2e.py
```
