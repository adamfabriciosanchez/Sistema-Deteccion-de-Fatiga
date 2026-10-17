from uuid import UUID
from datetime import datetime, date
from typing import Optional, List
import os
import shutil
from fastapi import APIRouter, Depends, Request, Form, Response, status, HTTPException, UploadFile, File
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from sqlalchemy import func, case, cast, Float

from app.core.database import get_db
from app.core.dependencies import get_current_user_optional, get_current_user, require_roles
from app.services.auth_service import AuthService
from app.services.despacho_service import DespachoService
from app.services.telemetria_service import TelemetriaService
from app.repositories.flota_repo import VehiculoRepository
from app.repositories.usuario_repo import UsuarioRepository
from app.repositories.despacho_repo import DespachoRepository
from app.repositories.telemetria_repo import TelemetriaRepository
from app.models.models import (
    Usuario,
    Conductor,
    Vehiculo,
    HojaDeRuta,
    AsignacionTripulacion,
    EstadoHoja,
    EstadoVehiculo,
    RolUsuario,
    TipoBus,
    TipoConductor,
    AccionAtencion,
    IncidenteAlerta,
    RegistroTelemetria,
    AtencionIncidente
)
from app.schemas.flota_schema import VehiculoCreate
from app.schemas.despacho_schema import HojaDeRutaCreate, TripulanteAsignacion, PreDespachoCreate
from app.schemas.telemetria_schema import AtencionIncidenteCreate

templates = Jinja2Templates(directory="app/templates")

def filter_sin_guion(val):
    if not val:
        return ""
    if hasattr(val, "value"):
        val = val.value
    return str(val).replace("_", " ")

templates.env.filters["sin_guion"] = filter_sin_guion

router = APIRouter(include_in_schema=False)

# Directorio base de uploads
UPLOAD_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "static", "uploads")
ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp", ".svg"}

def _save_upload(file: UploadFile, subfolder: str, entity_id: str) -> Optional[str]:
    """Guarda un archivo subido y retorna la URL relativa."""
    if not file or not file.filename:
        return None
    ext = os.path.splitext(file.filename)[1].lower()
    if ext not in ALLOWED_EXTENSIONS:
        return None
    dest_dir = os.path.join(UPLOAD_DIR, subfolder)
    os.makedirs(dest_dir, exist_ok=True)
    filename = f"{entity_id}{ext}"
    filepath = os.path.join(dest_dir, filename)
    with open(filepath, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)
    return f"/static/uploads/{subfolder}/{filename}"

# =========================================================
# VISTAS PÚBLICAS Y DE AUTENTICACIÓN
# =========================================================

@router.get("/", response_class=HTMLResponse)
def view_home(
    request: Request,
    current_user: Optional[Usuario] = Depends(get_current_user_optional)
):
    return templates.TemplateResponse(
        request=request,
        name="home.html",
        context={"current_user": current_user}
    )

@router.get("/login", response_class=HTMLResponse)
def view_login_page(
    request: Request,
    current_user: Optional[Usuario] = Depends(get_current_user_optional),
    error: Optional[str] = None
):
    if current_user:
        return RedirectResponse(url="/dashboard", status_code=status.HTTP_302_FOUND)
    
    return templates.TemplateResponse(
        request=request,
        name="login.html",
        context={"current_user": None, "error_msg": error}
    )

@router.post("/login", response_class=HTMLResponse)
def handle_web_login(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(get_db)
):
    service = AuthService(db)
    user = service.authenticate(email.strip(), password)
    if not user:
        return templates.TemplateResponse(
            request=request,
            name="login.html",
            context={
                "current_user": None,
                "error_msg": "Credenciales incorrectas o usuario inactivo. Verifique su correo y contraseña."
            },
            status_code=status.HTTP_401_UNAUTHORIZED
        )
    
    token_data = service.generate_token_data(user)
    token = token_data["access_token"]

    response = RedirectResponse(url="/dashboard", status_code=status.HTTP_303_SEE_OTHER)
    response.set_cookie(
        key="access_token",
        value=f"Bearer {token}",
        httponly=True,
        max_age=60 * 60 * 12,
        samesite="lax"
    )
    return response

@router.get("/logout")
def handle_logout():
    response = RedirectResponse(url="/login", status_code=status.HTTP_302_FOUND)
    response.delete_cookie("access_token")
    return response

@router.get("/dashboard", response_class=HTMLResponse)
def view_dashboard(
    request: Request,
    current_user: Usuario = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    stats = {}
    viaje_activo = None
    if current_user.rol == RolUsuario.ADMIN:
        stats = {
            "total_usuarios": db.query(Usuario).count(),
            "total_conductores": db.query(Conductor).count(),
            "total_vehiculos": db.query(Vehiculo).count(),
            "hojas_activas": db.query(HojaDeRuta).filter(HojaDeRuta.estado == EstadoHoja.EN_TRANSITO).count()
        }
    elif current_user.rol == RolUsuario.OPERADOR:
        stats = {
            "hojas_en_transito": db.query(HojaDeRuta).filter(HojaDeRuta.estado == EstadoHoja.EN_TRANSITO).count(),
            "hojas_pendientes": db.query(HojaDeRuta).filter(HojaDeRuta.estado == EstadoHoja.PRE_DESPACHO).count()
        }
    elif current_user.rol == RolUsuario.CONDUCTOR:
        despacho_repo = DespachoRepository(db)
        mis_hojas = despacho_repo.list_hojas_by_conductor(current_user.id)
        for h in mis_hojas:
            if h.estado in [EstadoHoja.PRE_DESPACHO, EstadoHoja.AUTORIZADA, EstadoHoja.EN_TRANSITO]:
                viaje_activo = h
                break

    return templates.TemplateResponse(
        request=request,
        name="dashboard.html",
        context={
            "current_user": current_user,
            "stats": stats,
            "viaje_activo": viaje_activo
        }
    )

# =========================================================
# VISTAS DE ADMINISTRACIÓN: FLOTA Y USUARIOS
# =========================================================

@router.get("/flota", response_class=HTMLResponse)
def view_flota(
    request: Request,
    current_user: Usuario = Depends(get_current_user),
    error: Optional[str] = None,
    success: Optional[str] = None,
    db: Session = Depends(get_db)
):
    repo = VehiculoRepository(db)
    vehiculos = repo.list_all()
    return templates.TemplateResponse(
        request=request,
        name="flota.html",
        context={
            "current_user": current_user,
            "vehiculos": vehiculos,
            "error_msg": error,
            "success_msg": success
        }
    )

@router.post("/flota/nuevo")
def handle_nuevo_bus(
    numero_interno: str = Form(...),
    placa: str = Form(...),
    marca: str = Form(...),
    modelo: str = Form(...),
    tipo_bus: str = Form(...),
    capacidad_pasajeros: Optional[int] = Form(54),
    chasis: Optional[str] = Form(None),
    carroceria: Optional[str] = Form(None),
    anio_fabricacion: Optional[int] = Form(None),
    ubicacion_actual: Optional[str] = Form("Cochabamba"),
    foto: Optional[UploadFile] = File(None),
    current_user: Usuario = Depends(require_roles([RolUsuario.ADMIN])),
    db: Session = Depends(get_db)
):
    repo = VehiculoRepository(db)
    bus = repo.create(VehiculoCreate(
        numero_interno=numero_interno.strip(),
        placa=placa.strip().upper(),
        modelo=modelo.strip(),
        marca=marca.strip(),
        tipo_bus=TipoBus(tipo_bus),
        capacidad_pasajeros=capacidad_pasajeros,
        chasis=chasis.strip() if chasis else None,
        carroceria=carroceria.strip() if carroceria else None,
        anio_fabricacion=anio_fabricacion,
        ubicacion_actual=ubicacion_actual.strip() if ubicacion_actual else "Cochabamba"
    ))
    # Subir foto si fue proporcionada
    if foto and foto.filename:
        foto_url = _save_upload(foto, "vehiculos", str(bus.id))
        if foto_url:
            repo.update(bus.id, foto_url=foto_url)
    return RedirectResponse(url="/flota?success=Vehiculo+registrado+con+exito", status_code=status.HTTP_303_SEE_OTHER)

@router.post("/flota/{vehiculo_id}/editar")
def handle_editar_bus(
    vehiculo_id: UUID,
    numero_interno: str = Form(...),
    placa: str = Form(...),
    marca: str = Form(...),
    modelo: str = Form(...),
    tipo_bus: str = Form(...),
    capacidad_pasajeros: Optional[int] = Form(54),
    estado: Optional[str] = Form(None),
    ubicacion_actual: Optional[str] = Form(None),
    foto: Optional[UploadFile] = File(None),
    current_user: Usuario = Depends(require_roles([RolUsuario.ADMIN])),
    db: Session = Depends(get_db)
):
    repo = VehiculoRepository(db)
    bus = repo.get_by_id(vehiculo_id)
    if not bus:
        return RedirectResponse(url="/flota?error=Vehiculo+no+encontrado", status_code=status.HTTP_303_SEE_OTHER)

    # Regla: Si el bus está EN_TRANSITO, no se puede cambiar su estado manualmente
    nuevo_estado = bus.estado
    if estado and estado != bus.estado.value:
        if bus.estado == EstadoVehiculo.EN_TRANSITO:
            return RedirectResponse(
                url="/flota?error=No+se+puede+modificar+el+estado+de+un+bus+EN+TRANSITO",
                status_code=status.HTTP_303_SEE_OTHER
            )
        nuevo_estado = EstadoVehiculo(estado)

    # Subir foto si fue proporcionada
    foto_url = bus.foto_url
    if foto and foto.filename:
        new_foto = _save_upload(foto, "vehiculos", str(vehiculo_id))
        if new_foto:
            foto_url = new_foto

    repo.update(
        vehiculo_id,
        numero_interno=numero_interno.strip(),
        placa=placa.strip().upper(),
        marca=marca.strip(),
        modelo=modelo.strip(),
        tipo_bus=TipoBus(tipo_bus),
        capacidad_pasajeros=capacidad_pasajeros,
        estado=nuevo_estado,
        ubicacion_actual=ubicacion_actual.strip() if ubicacion_actual else bus.ubicacion_actual,
        foto_url=foto_url
    )
    return RedirectResponse(url="/flota?success=Vehiculo+actualizado+exitosamente", status_code=status.HTTP_303_SEE_OTHER)


@router.get("/usuarios", response_class=HTMLResponse)
def view_usuarios(
    request: Request,
    error: Optional[str] = None,
    success: Optional[str] = None,
    current_user: Usuario = Depends(require_roles([RolUsuario.ADMIN])),
    db: Session = Depends(get_db)
):
    repo = UsuarioRepository(db)
    usuarios = repo.list_all()
    return templates.TemplateResponse(
        request=request,
        name="usuarios.html",
        context={
            "current_user": current_user,
            "usuarios": usuarios,
            "error_msg": error,
            "success_msg": success
        }
    )

@router.post("/usuarios/nuevo")
def handle_nuevo_usuario(
    nombre: str = Form(...),
    apellido: str = Form(...),
    ci: str = Form(...),
    email: str = Form(...),
    password: str = Form(...),
    rol: str = Form(...),
    licencia_conducir: Optional[str] = Form(None),
    categoria_licencia: Optional[str] = Form(None),
    ubicacion_actual: Optional[str] = Form("Cochabamba"),
    foto: Optional[UploadFile] = File(None),
    current_user: Usuario = Depends(require_roles([RolUsuario.ADMIN])),
    db: Session = Depends(get_db)
):
    from app.models.models import Rol
    from app.core.security import get_password_hash

    # Validar si el rol es conductor, debe tener licencia
    if rol == "CONDUCTOR" and (not licencia_conducir or not categoria_licencia):
        return RedirectResponse(url="/usuarios?error=Conductor+debe+tener+licencia+y+categoria", status_code=status.HTTP_303_SEE_OTHER)

    hashed_password = get_password_hash(password)
    rol_db = db.query(Rol).filter(Rol.nombre == rol).first()
    if not rol_db:
        return RedirectResponse(url="/usuarios?error=Rol+invalido", status_code=status.HTTP_303_SEE_OTHER)

    # Validar duplicados de CI o Email
    repo = UsuarioRepository(db)
    if repo.get_by_email(email.strip()):
        return RedirectResponse(url="/usuarios?error=Ya+existe+un+usuario+con+este+correo", status_code=status.HTTP_303_SEE_OTHER)
    if repo.get_by_ci(ci.strip()):
        return RedirectResponse(url="/usuarios?error=Ya+existe+un+usuario+con+este+CI", status_code=status.HTTP_303_SEE_OTHER)

    nuevo_user = Usuario(
        ci=ci.strip(),
        nombre=nombre.strip(),
        apellido=apellido.strip(),
        email=email.strip().lower(),
        password_hash=hashed_password,
        rol_id=rol_db.id,
        estado=True
    )
    db.add(nuevo_user)
    db.flush()

    if rol == "CONDUCTOR":
        nuevo_conductor = Conductor(
            id=nuevo_user.id,
            licencia_conducir=licencia_conducir.strip(),
            categoria_licencia=categoria_licencia.strip(),
            puntaje_promedio=5.00,
            ubicacion_actual=ubicacion_actual.strip() if ubicacion_actual else "Cochabamba"
        )
        db.add(nuevo_conductor)
    
    db.commit()

    # Subir foto si fue proporcionada
    if foto and foto.filename:
        foto_url = _save_upload(foto, "usuarios", str(nuevo_user.id))
        if foto_url:
            nuevo_user.foto_url = foto_url
            db.commit()

    return RedirectResponse(url="/usuarios?success=Usuario+creado+exitosamente", status_code=status.HTTP_303_SEE_OTHER)

@router.post("/usuarios/{usuario_id}/editar")
def handle_editar_usuario(
    usuario_id: UUID,
    nombre: str = Form(...),
    apellido: str = Form(...),
    ci: str = Form(...),
    email: str = Form(...),
    estado: Optional[str] = Form(None),
    licencia_conducir: Optional[str] = Form(None),
    categoria_licencia: Optional[str] = Form(None),
    ubicacion_actual: Optional[str] = Form(None),
    foto: Optional[UploadFile] = File(None),
    current_user: Usuario = Depends(require_roles([RolUsuario.ADMIN])),
    db: Session = Depends(get_db)
):
    repo = UsuarioRepository(db)
    user = repo.get_by_id(usuario_id)
    
    if not user:
        return RedirectResponse(url="/usuarios?error=Usuario+no+encontrado", status_code=status.HTTP_303_SEE_OTHER)

    user.nombre = nombre.strip()
    user.apellido = apellido.strip()
    user.ci = ci.strip()
    user.email = email.strip().lower()
    user.estado = True if estado == "on" else False

    # Subir foto si fue proporcionada
    if foto and foto.filename:
        foto_url = _save_upload(foto, "usuarios", str(usuario_id))
        if foto_url:
            user.foto_url = foto_url

    if user.rol.value == "CONDUCTOR":
        if user.conductor:
            if licencia_conducir:
                user.conductor.licencia_conducir = licencia_conducir.strip()
            if categoria_licencia:
                user.conductor.categoria_licencia = categoria_licencia.strip()
            if ubicacion_actual:
                user.conductor.ubicacion_actual = ubicacion_actual.strip()
        else:
            if licencia_conducir and categoria_licencia:
                db_conductor = Conductor(
                    id=user.id,
                    licencia_conducir=licencia_conducir.strip(),
                    categoria_licencia=categoria_licencia.strip(),
                    puntaje_promedio=5.00,
                    ubicacion_actual=ubicacion_actual.strip() if ubicacion_actual else "Cochabamba"
                )
                db.add(db_conductor)

    db.commit()
    return RedirectResponse(url="/usuarios?success=Usuario+actualizado+exitosamente", status_code=status.HTTP_303_SEE_OTHER)

# =========================================================
# VISTAS DE HOJAS DE RUTA (DESPACHO Y REGLA ATT)
# Accesible por ADMIN (lectura/escritura) y OPERADOR (solo lectura)
# =========================================================

@router.get("/hojas-ruta", response_class=HTMLResponse)
def view_hojas_ruta(
    request: Request,
    estado: Optional[str] = None,
    busqueda: Optional[str] = None,
    error: Optional[str] = None,
    success: Optional[str] = None,
    current_user: Usuario = Depends(require_roles([RolUsuario.ADMIN, RolUsuario.OPERADOR])),
    db: Session = Depends(get_db)
):
    despacho_repo = DespachoRepository(db)
    flota_repo = VehiculoRepository(db)
    usuario_repo = UsuarioRepository(db)

    filtro_estado = EstadoHoja(estado) if estado and estado in EstadoHoja._value2member_map_ else None
    hojas = despacho_repo.list_hojas(estado=filtro_estado, busqueda=busqueda)
    vehiculos_disponibles = flota_repo.list_disponibles()
    conductores = usuario_repo.list_conductores()

    return templates.TemplateResponse(
        request=request,
        name="hojas_ruta.html",
        context={
            "current_user": current_user,
            "hojas": hojas,
            "vehiculos_disponibles": vehiculos_disponibles,
            "conductores": conductores,
            "estado_filtro": estado,
            "busqueda_filtro": busqueda,
            "error_msg": error,
            "success_msg": success
        }
    )

@router.post("/hojas-ruta/nuevo")
def handle_nueva_hoja(
    codigo_hoja: str = Form(...),
    fecha_salida: str = Form(...),
    vehiculo_id: UUID = Form(...),
    origen_ciudad: str = Form(...),
    origen_terminal: str = Form(...),
    destino_ciudad: str = Form(...),
    destino_terminal: str = Form(...),
    fecha_llegada_estimada: str = Form(...),
    conductor_principal_id: UUID = Form(...),
    conductor_relevo_id: Optional[UUID] = Form(None),
    current_user: Usuario = Depends(require_roles([RolUsuario.ADMIN])),
    db: Session = Depends(get_db)
):
    service = DespachoService(db)
    
    tripulantes = [
        TripulanteAsignacion(conductor_id=conductor_principal_id, tipo_conductor=TipoConductor.PRINCIPAL)
    ]
    if conductor_relevo_id:
        tripulantes.append(
            TripulanteAsignacion(conductor_id=conductor_relevo_id, tipo_conductor=TipoConductor.RELEVO)
        )

    try:
        dt_salida = datetime.fromisoformat(fecha_salida)
        dt_llegada = datetime.fromisoformat(fecha_llegada_estimada)
        duracion_hrs = round((dt_llegada - dt_salida).total_seconds() / 3600.0, 2)
        service.programar_hoja_de_ruta(HojaDeRutaCreate(
            codigo_hoja=codigo_hoja,
            vehiculo_id=vehiculo_id,
            origen_ciudad=origen_ciudad,
            origen_terminal=origen_terminal,
            destino_ciudad=destino_ciudad,
            destino_terminal=destino_terminal,
            duracion_estimada_hrs=duracion_hrs,
            fecha_salida=dt_salida,
            fecha_llegada_estimada=dt_llegada,
            tripulantes=tripulantes
        ))
        return RedirectResponse(
            url="/hojas-ruta?success=Hoja+de+ruta+programada+correctamente",
            status_code=status.HTTP_303_SEE_OTHER
        )
    except HTTPException as e:
        return RedirectResponse(
            url=f"/hojas-ruta?error={e.detail}",
            status_code=status.HTTP_303_SEE_OTHER
        )

# =========================================================
# VISTAS DE PRE-DESPACHO (ALCOTEST EN TERMINAL)
# =========================================================

@router.get("/pre-despacho", response_class=HTMLResponse)
def view_pre_despacho(
    request: Request,
    error: Optional[str] = None,
    success: Optional[str] = None,
    current_user: Usuario = Depends(require_roles([RolUsuario.ADMIN])),
    db: Session = Depends(get_db)
):
    despacho_repo = DespachoRepository(db)
    usuario_repo = UsuarioRepository(db)
    hojas_pendientes = despacho_repo.list_hojas(estado=EstadoHoja.PRE_DESPACHO)
    hojas_autorizadas = despacho_repo.list_hojas(estado=EstadoHoja.AUTORIZADA)
    conductores_disponibles = usuario_repo.list_conductores()

    return templates.TemplateResponse(
        request=request,
        name="pre_despacho.html",
        context={
            "current_user": current_user,
            "hojas_pendientes": hojas_pendientes,
            "hojas_autorizadas": hojas_autorizadas,
            "conductores_disponibles": conductores_disponibles,
            "error_msg": error,
            "success_msg": success
        }
    )

@router.post("/pre-despacho/validar")
def handle_validar_alcotest(
    hoja_de_ruta_id: UUID = Form(...),
    resultado_alcotest: Optional[float] = Form(0.0),
    resultado_alcotest_principal: Optional[float] = Form(None),
    resultado_alcotest_relevo: Optional[float] = Form(None),
    observaciones: Optional[str] = Form(None),
    current_user: Usuario = Depends(require_roles([RolUsuario.ADMIN])),
    db: Session = Depends(get_db)
):
    service = DespachoService(db)
    try:
        p_val = resultado_alcotest_principal if resultado_alcotest_principal is not None else resultado_alcotest
        pre = service.registrar_pre_despacho(
            PreDespachoCreate(
                hoja_de_ruta_id=hoja_de_ruta_id,
                resultado_alcotest=p_val,
                resultado_alcotest_principal=p_val,
                resultado_alcotest_relevo=resultado_alcotest_relevo,
                observaciones=observaciones
            ),
            operador_actual=current_user
        )
        if pre.aprobado:
            msg = "Pre-despacho+APROBADO.+Alcotest+0.00+mg/L+para+toda+la+tripulaci%C3%B3n.+Unidad+AUTORIZADA."
        else:
            detalles_fallo = []
            if pre.aprobado_principal is False:
                detalles_fallo.append(f"Principal:+{pre.resultado_alcotest_principal}+mg/L")
            if pre.aprobado_relevo is False:
                detalles_fallo.append(f"Relevo:+{pre.resultado_alcotest_relevo}+mg/L")
            fallo_str = "+|+".join(detalles_fallo) if detalles_fallo else f"{resultado_alcotest}+mg/L"
            msg = f"Pre-despacho+RECHAZADO.+Alcotest+positivo+({fallo_str}).+Reasigne+al+conductor+reprobado+antes+de+autorizar."
        return RedirectResponse(url=f"/pre-despacho?success={msg}", status_code=status.HTTP_303_SEE_OTHER)
    except HTTPException as e:
        return RedirectResponse(url=f"/pre-despacho?error={e.detail}", status_code=status.HTTP_303_SEE_OTHER)

@router.post("/hojas-ruta/{hoja_id}/reasignar")
def handle_reasignar_conductor_web(
    hoja_id: UUID,
    tipo_conductor: str = Form(...),
    nuevo_conductor_id: UUID = Form(...),
    current_user: Usuario = Depends(require_roles([RolUsuario.ADMIN])),
    db: Session = Depends(get_db)
):
    service = DespachoService(db)
    try:
        service.reasignar_conductor(hoja_id, TipoConductor(tipo_conductor), nuevo_conductor_id)
        return RedirectResponse(
            url="/pre-despacho?success=Conductor+reasignado+exitosamente.+Listo+para+nuevo+control+de+alcotest",
            status_code=status.HTTP_303_SEE_OTHER
        )
    except HTTPException as e:
        return RedirectResponse(url=f"/pre-despacho?error={e.detail}", status_code=status.HTTP_303_SEE_OTHER)

@router.post("/hojas-ruta/{hoja_id}/iniciar-transito-web")
def handle_iniciar_transito_web(
    hoja_id: UUID,
    current_user: Usuario = Depends(require_roles([RolUsuario.ADMIN, RolUsuario.OPERADOR])),
    db: Session = Depends(get_db)
):
    service = DespachoService(db)
    try:
        service.autorizar_salida_transito(hoja_id)
        return RedirectResponse(
            url="/pre-despacho?success=Bus+inici%C3%B3+tr%C3%A1nsito+en+carretera+satisfactoriamente",
            status_code=status.HTTP_303_SEE_OTHER
        )
    except HTTPException as e:
        return RedirectResponse(url=f"/pre-despacho?error={e.detail}", status_code=status.HTTP_303_SEE_OTHER)

# =========================================================
# PERFIL DEL CONDUCTOR (MÓVIL / INICIAR Y FINALIZAR VIAJE)
# =========================================================

@router.get("/mi-hoja", response_class=HTMLResponse)
def view_mi_hoja(
    request: Request,
    error: Optional[str] = None,
    success: Optional[str] = None,
    current_user: Usuario = Depends(require_roles([RolUsuario.CONDUCTOR])),
    db: Session = Depends(get_db)
):
    despacho_repo = DespachoRepository(db)
    mis_hojas = despacho_repo.list_hojas_by_conductor(current_user.id)

    viaje_activo = None
    historial_viajes = []

    for h in mis_hojas:
        if h.estado in [EstadoHoja.PRE_DESPACHO, EstadoHoja.AUTORIZADA, EstadoHoja.EN_TRANSITO] and not viaje_activo:
            viaje_activo = h
        else:
            historial_viajes.append(h)

    # Determinar si en el viaje activo es PRINCIPAL o RELEVO
    es_principal = False
    rol_en_viaje = "NO ASIGNADO"
    alertas_pps = []
    if viaje_activo:
        for t in viaje_activo.tripulacion:
            if t.conductor_id == current_user.id:
                rol_en_viaje = t.tipo_conductor.value
                es_principal = (t.tipo_conductor == TipoConductor.PRINCIPAL)
                break
        
        # Consultar incidentes con atención PPS de este viaje
        from app.models.models import IncidenteAlerta
        alertas_pps = (
            db.query(IncidenteAlerta)
            .filter(IncidenteAlerta.hoja_de_ruta_id == viaje_activo.id)
            .order_by(IncidenteAlerta.timestamp_evento.desc())
            .all()
        )

    base_actual = current_user.conductor.ubicacion_actual if current_user.conductor else "Cochabamba"

    return templates.TemplateResponse(
        request=request,
        name="mi_hoja.html",
        context={
            "current_user": current_user,
            "viaje_activo": viaje_activo,
            "historial_viajes": historial_viajes,
            "es_principal": es_principal,
            "rol_en_viaje": rol_en_viaje,
            "base_actual": base_actual,
            "alertas_pps": alertas_pps,
            "error_msg": error,
            "success_msg": success
        }
    )

@router.post("/mi-hoja/{hoja_id}/iniciar")
def handle_conductor_iniciar_viaje(
    hoja_id: UUID,
    current_user: Usuario = Depends(require_roles([RolUsuario.CONDUCTOR])),
    db: Session = Depends(get_db)
):
    despacho_repo = DespachoRepository(db)
    hoja = despacho_repo.get_hoja_by_id(hoja_id)
    if not hoja:
        return RedirectResponse(url="/mi-hoja?error=Hoja+de+ruta+no+encontrada", status_code=status.HTTP_303_SEE_OTHER)

    # Validar que sea el conductor PRINCIPAL
    es_principal = any(
        t.conductor_id == current_user.id and t.tipo_conductor == TipoConductor.PRINCIPAL
        for t in hoja.tripulacion
    )
    if not es_principal:
        return RedirectResponse(
            url="/mi-hoja?error=Solo+el+conductor+PRINCIPAL+puede+iniciar+el+viaje",
            status_code=status.HTTP_303_SEE_OTHER
        )

    service = DespachoService(db)
    try:
        service.autorizar_salida_transito(hoja_id)
        return RedirectResponse(url="/mi-hoja?success=Viaje+iniciado+correctamente.+Buen+camino.", status_code=status.HTTP_303_SEE_OTHER)
    except HTTPException as e:
        return RedirectResponse(url=f"/mi-hoja?error={e.detail}", status_code=status.HTTP_303_SEE_OTHER)

@router.post("/mi-hoja/{hoja_id}/finalizar")
def handle_conductor_finalizar_viaje(
    hoja_id: UUID,
    current_user: Usuario = Depends(require_roles([RolUsuario.CONDUCTOR])),
    db: Session = Depends(get_db)
):
    despacho_repo = DespachoRepository(db)
    hoja = despacho_repo.get_hoja_by_id(hoja_id)
    if not hoja:
        return RedirectResponse(url="/mi-hoja?error=Hoja+de+ruta+no+encontrada", status_code=status.HTTP_303_SEE_OTHER)

    es_principal = any(
        t.conductor_id == current_user.id and t.tipo_conductor == TipoConductor.PRINCIPAL
        for t in hoja.tripulacion
    )
    if not es_principal:
        return RedirectResponse(
            url="/mi-hoja?error=Solo+el+conductor+PRINCIPAL+puede+finalizar+el+viaje",
            status_code=status.HTTP_303_SEE_OTHER
        )

    service = DespachoService(db)
    try:
        service.finalizar_viaje(hoja_id)
        return RedirectResponse(url="/mi-hoja?success=Viaje+finalizado+exitosamente.+Unidad+en+destino.", status_code=status.HTTP_303_SEE_OTHER)
    except HTTPException as e:
        return RedirectResponse(url=f"/mi-hoja?error={e.detail}", status_code=status.HTTP_303_SEE_OTHER)

# =========================================================
# VISTA DEL CENTRO DE MONITOREO EN VIVO (LEAFLET.JS Y PPS)
# =========================================================

@router.get("/monitoreo", response_class=HTMLResponse)
@router.get("/monitoreo/", response_class=HTMLResponse)
def view_monitoreo(
    request: Request,
    hoja_id: Optional[UUID] = None,
    current_user: Usuario = Depends(require_roles([RolUsuario.ADMIN, RolUsuario.OPERADOR])),
    db: Session = Depends(get_db)
):
    """
    Vista interactiva del Centro de Control con mapa satelital Leaflet.js
    y Protocolo de Parada Segura (PPS).
    """
    # Obtener todas las hojas de ruta priorizando EN_TRANSITO para el panel de simulación
    despacho_repo = DespachoRepository(db)
    todas_las_hojas = despacho_repo.list_hojas()
    prioridad_estado = {
        EstadoHoja.EN_TRANSITO: 0,
        EstadoHoja.AUTORIZADA: 1,
        EstadoHoja.PRE_DESPACHO: 2,
        EstadoHoja.BORRADOR: 3,
        EstadoHoja.FINALIZADA: 4,
        EstadoHoja.CANCELADA: 5
    }
    hojas_simulables = sorted(
        todas_las_hojas,
        key=lambda h: (prioridad_estado.get(h.estado, 99), str(h.fecha_salida or ""))
    )

    # Garantizar que cada hoja tenga identificado el ID del conductor para el simulador
    for h in hojas_simulables:
        c_id = ""
        for t in h.tripulacion:
            if t.tipo_conductor == TipoConductor.PRINCIPAL and t.conductor_id:
                c_id = str(t.conductor_id)
                break
        if not c_id and h.tripulacion and h.tripulacion[0].conductor_id:
            c_id = str(h.tripulacion[0].conductor_id)
        h.conductor_simulacion_id = c_id

    return templates.TemplateResponse(
        request=request,
        name="monitoreo.html",
        context={
            "current_user": current_user,
            "filtro_hoja_id": str(hoja_id) if hoja_id else None,
            "hojas_simulables": hojas_simulables
        }
    )

@router.post("/monitoreo/atender")
async def handle_atender_incidente_web(
    incidente_id: UUID = Form(...),
    accion_tomada: AccionAtencion = Form(...),
    mensaje_enviado: Optional[str] = Form(None),
    audio_url: Optional[str] = Form(None),
    current_user: Usuario = Depends(require_roles([RolUsuario.ADMIN, RolUsuario.OPERADOR])),
    db: Session = Depends(get_db)
):
    """
    Procesa el formulario web del modal Protocolo de Parada Segura (PPS).
    """
    service = TelemetriaService(db)
    try:
        await service.atender_incidente(
            AtencionIncidenteCreate(
                incidente_id=incidente_id,
                accion_tomada=accion_tomada,
                mensaje_enviado=mensaje_enviado.strip() if mensaje_enviado else None,
                audio_url=audio_url.strip() if audio_url else None
            ),
            operador_actual=current_user
        )
        return RedirectResponse(
            url="/monitoreo?success=Atenci%C3%B3n+de+incidente+PPS+registrada+exitosamente",
            status_code=status.HTTP_303_SEE_OTHER
        )
    except HTTPException as e:
        return RedirectResponse(
            url=f"/monitoreo?error={e.detail}",
            status_code=status.HTTP_303_SEE_OTHER
        )

# =========================================================
# VISTA DE REPORTES DINÁMICOS
# =========================================================

@router.get("/reportes", response_class=HTMLResponse)
@router.get("/reportes/", response_class=HTMLResponse)
def view_reportes(
    request: Request,
    tipo: Optional[str] = None,
    fecha_desde: Optional[str] = None,
    fecha_hasta: Optional[str] = None,
    current_user: Usuario = Depends(require_roles([RolUsuario.ADMIN, RolUsuario.OPERADOR])),
    db: Session = Depends(get_db)
):
    """
    Vista de Reportes Dinámicos generados a partir de datos de simulación/telemetría.
    """
    from sqlalchemy.orm import joinedload

    # Datos para los reportes
    resumen_viajes = []
    resumen_incidentes = []
    resumen_fatiga = []

    # Reporte 1: Resumen de Viajes
    hojas = (
        db.query(HojaDeRuta)
        .options(
            joinedload(HojaDeRuta.vehiculo),
            joinedload(HojaDeRuta.tripulacion).joinedload(
                AsignacionTripulacion.conductor
            ).joinedload(Conductor.usuario)
        )
        .order_by(HojaDeRuta.fecha_salida.desc())
        .limit(50)
        .all()
    )
    for h in hojas:
        # Contar registros de telemetría
        n_tele = db.query(func.count(RegistroTelemetria.id)).filter(
            RegistroTelemetria.hoja_de_ruta_id == h.id
        ).scalar()
        n_inc = db.query(func.count(IncidenteAlerta.id)).filter(
            IncidenteAlerta.hoja_de_ruta_id == h.id
        ).scalar()
        resumen_viajes.append({
            "hoja": h,
            "total_telemetrias": n_tele,
            "total_incidentes": n_inc
        })

    # Reporte 2: Resumen de Incidentes
    incidentes = (
        db.query(IncidenteAlerta)
        .options(
            joinedload(IncidenteAlerta.hoja_de_ruta).joinedload(HojaDeRuta.vehiculo),
            joinedload(IncidenteAlerta.conductor).joinedload(Conductor.usuario),
            joinedload(IncidenteAlerta.atencion)
        )
        .order_by(IncidenteAlerta.timestamp_evento.desc())
        .limit(100)
        .all()
    )
    resumen_incidentes = incidentes

    # Reporte 3: Resumen de Fatiga por Conductor
    fatiga_query = (
        db.query(
            IncidenteAlerta.conductor_id,
            func.count(IncidenteAlerta.id).label("total_incidentes"),
            func.avg(cast(IncidenteAlerta.indice_fatiga_if, Float)).label("promedio_if"),
            func.max(cast(IncidenteAlerta.indice_fatiga_if, Float)).label("max_if"),
            func.avg(cast(IncidenteAlerta.perclos_porcentaje, Float)).label("promedio_perclos"),
            func.count(case((IncidenteAlerta.tipo_incidente == 'FATIGA_CRITICA', 1))).label("fatiga_critica"),
            func.count(case((IncidenteAlerta.tipo_incidente == 'SOMNOLENCIA_PREVENTIVA', 1))).label("somnolencia"),
            func.count(case((IncidenteAlerta.tipo_incidente == 'EXCESO_VELOCIDAD', 1))).label("exceso_vel"),
        )
        .group_by(IncidenteAlerta.conductor_id)
        .all()
    )
    for row in fatiga_query:
        conductor = db.query(Conductor).options(joinedload(Conductor.usuario)).filter(Conductor.id == row.conductor_id).first()
        if conductor and conductor.usuario:
            resumen_fatiga.append({
                "conductor": conductor,
                "total_incidentes": row.total_incidentes,
                "promedio_if": round(float(row.promedio_if or 0), 3),
                "max_if": round(float(row.max_if or 0), 3),
                "promedio_perclos": round(float(row.promedio_perclos or 0), 2),
                "fatiga_critica": row.fatiga_critica,
                "somnolencia": row.somnolencia,
                "exceso_vel": row.exceso_vel
            })

    return templates.TemplateResponse(
        request=request,
        name="reportes.html",
        context={
            "current_user": current_user,
            "resumen_viajes": resumen_viajes,
            "resumen_incidentes": resumen_incidentes,
            "resumen_fatiga": resumen_fatiga,
            "tipo_reporte": tipo
        }
    )
