from app.schemas.usuario_schema import (
    LoginRequest,
    TokenResponse,
    UsuarioBase,
    UsuarioCreate,
    UsuarioOut,
    ConductorBase,
    ConductorOut,
)
from app.schemas.flota_schema import (
    VehiculoBase,
    VehiculoCreate,
    VehiculoOut,
)
from app.schemas.despacho_schema import (
    TripulanteAsignacion,
    AsignacionTripulacionOut,
    HojaDeRutaCreate,
    HojaDeRutaOut,
    PreDespachoCreate,
    PreDespachoOut,
)
from app.schemas.telemetria_schema import (
    TelemetriaPayload,
    TelemetriaOut,
    IncidenteAlertaCreate,
    IncidenteAlertaOut,
    BusSnapshot,
)

__all__ = [
    "LoginRequest",
    "TokenResponse",
    "UsuarioBase",
    "UsuarioCreate",
    "UsuarioOut",
    "ConductorBase",
    "ConductorOut",
    "VehiculoBase",
    "VehiculoCreate",
    "VehiculoOut",
    "TripulanteAsignacion",
    "AsignacionTripulacionOut",
    "HojaDeRutaCreate",
    "HojaDeRutaOut",
    "PreDespachoCreate",
    "PreDespachoOut",
    "TelemetriaPayload",
    "TelemetriaOut",
    "IncidenteAlertaCreate",
    "IncidenteAlertaOut",
    "BusSnapshot",
]
