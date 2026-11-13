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
from app.repositories.camara_repo import CamaraRepository
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
    AtencionIncidente,
    CamaraVehiculo
)
from app.schemas.flota_schema import VehiculoCreate
from app.services.rutas_oficiales import TERMINALES_POR_CIUDAD, get_coordenadas_terminal
from app.schemas.despacho_schema import HojaDeRutaCreate, TripulanteAsignacion, PreDespachoCreate
from app.schemas.telemetria_schema import AtencionIncidenteCreate

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TEMPLATES_DIR = os.path.join(BASE_DIR, "templates")
templates = Jinja2Templates(directory=TEMPLATES_DIR)

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

    # Calcular próximo número interno correlativo TC-XXX
    max_num = 0
    for b in vehiculos:
        if b.numero_interno and b.numero_interno.startswith("TC-"):
            try:
                num_part = int(b.numero_interno.split("-")[1])
                if num_part > max_num:
                    max_num = num_part
            except (ValueError, IndexError):
                pass
    proximo_numero_interno = f"TC-{max_num + 1:03d}"

    return templates.TemplateResponse(
        request=request,
        name="flota.html",
        context={
            "current_user": current_user,
            "vehiculos": vehiculos,
            "proximo_numero_interno": proximo_numero_interno,
            "terminales_por_ciudad": TERMINALES_POR_CIUDAD,
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
    soat_numero: Optional[str] = Form(None),
    soat_vigencia: Optional[str] = Form(None),
    ubicacion_actual: Optional[str] = Form("Cochabamba"),
    terminal_actual: Optional[str] = Form(None),
    foto: Optional[UploadFile] = File(None),
    current_user: Usuario = Depends(require_roles([RolUsuario.ADMIN])),
    db: Session = Depends(get_db)
):
    import re
    # Validar formato de placa boliviana
    placa_clean = placa.strip().upper()
    if not re.match(r"^[0-9]{3,4}-?[A-Z]{3}$", placa_clean):
        return RedirectResponse(url="/flota?error=Formato+de+placa+invalido.+Ej.+1001-LPZ", status_code=status.HTTP_303_SEE_OTHER)
    if "-" not in placa_clean:
        placa_clean = f"{placa_clean[:-3]}-{placa_clean[-3:]}"

    # Validar marcas permitidas
    marcas_validas = ["Mercedes-Benz", "Scania", "Volvo", "MAN", "Marcopolo"]
    if marca.strip() not in marcas_validas:
        return RedirectResponse(url="/flota?error=Marca+no+autorizada", status_code=status.HTTP_303_SEE_OTHER)

    repo = VehiculoRepository(db)
    dt_soat = None
    if soat_vigencia and soat_vigencia.strip():
        try:
            dt_soat = datetime.strptime(soat_vigencia.strip(), "%Y-%m-%d").date()
        except ValueError:
            pass

    bus = repo.create(VehiculoCreate(
        numero_interno=numero_interno.strip().upper(),
        placa=placa_clean,
        modelo=modelo.strip(),
        marca=marca.strip(),
        tipo_bus=TipoBus(tipo_bus),
        capacidad_pasajeros=capacidad_pasajeros,
        chasis=chasis.strip() if chasis else None,
        carroceria=carroceria.strip() if carroceria else None,
        anio_fabricacion=anio_fabricacion,
        soat_numero=soat_numero.strip().upper() if soat_numero else None,
        soat_vigencia=dt_soat,
        ubicacion_actual=ubicacion_actual.strip() if ubicacion_actual else "Cochabamba",
        terminal_actual=terminal_actual.strip() if terminal_actual else None
    ))

    # Asegurar que el bus tenga su cámara vinculada CAM-{numero_interno}
    cam_code = f"CAM-{bus.numero_interno}"
    cam_existente = db.query(CamaraVehiculo).filter(CamaraVehiculo.vehiculo_id == bus.id).first()
    if not cam_existente:
        nueva_cam = CamaraVehiculo(
            vehiculo_id=bus.id,
            codigo_camara=cam_code,
            marca_modelo=f"Cámara Cabina {bus.marca}",
            tipo_dispositivo="CELULAR_CONDUCTOR",
            resolucion="1280x720",
            estado="ACTIVA"
        )
        db.add(nueva_cam)
        db.commit()

    # Subir foto si fue proporcionada
    if foto and foto.filename:
        foto_url = _save_upload(foto, "vehiculos", str(bus.id))
        if foto_url:
            repo.update(bus.id, foto_url=foto_url)
    return RedirectResponse(url="/flota?success=Vehiculo+y+camara+asociada+registrados+con+exito", status_code=status.HTTP_303_SEE_OTHER)

@router.post("/flota/{vehiculo_id}/editar")
def handle_editar_bus(
    vehiculo_id: UUID,
    numero_interno: str = Form(...),
    placa: str = Form(...),
    marca: str = Form(...),
    modelo: str = Form(...),
    tipo_bus: str = Form(...),
    capacidad_pasajeros: Optional[int] = Form(54),
    soat_numero: Optional[str] = Form(None),
    soat_vigencia: Optional[str] = Form(None),
    estado: Optional[str] = Form(None),
    ubicacion_actual: Optional[str] = Form(None),
    terminal_actual: Optional[str] = Form(None),
    foto: Optional[UploadFile] = File(None),
    current_user: Usuario = Depends(require_roles([RolUsuario.ADMIN])),
    db: Session = Depends(get_db)
):
    import re
    placa_clean = placa.strip().upper()
    if not re.match(r"^[0-9]{3,4}-?[A-Z]{3}$", placa_clean):
        return RedirectResponse(url="/flota?error=Formato+de+placa+invalido.+Ej.+1001-LPZ", status_code=status.HTTP_303_SEE_OTHER)
    if "-" not in placa_clean:
        placa_clean = f"{placa_clean[:-3]}-{placa_clean[-3:]}"

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

    dt_soat = bus.soat_vigencia
    if soat_vigencia and soat_vigencia.strip():
        try:
            dt_soat = datetime.strptime(soat_vigencia.strip(), "%Y-%m-%d").date()
        except ValueError:
            pass

    repo.update(
        vehiculo_id,
        numero_interno=numero_interno.strip().upper(),
        placa=placa_clean,
        marca=marca.strip(),
        modelo=modelo.strip(),
        tipo_bus=TipoBus(tipo_bus),
        capacidad_pasajeros=capacidad_pasajeros,
        soat_numero=soat_numero.strip().upper() if soat_numero else bus.soat_numero,
        soat_vigencia=dt_soat,
        estado=nuevo_estado,
        ubicacion_actual=ubicacion_actual.strip() if ubicacion_actual else bus.ubicacion_actual,
        terminal_actual=terminal_actual.strip() if terminal_actual else bus.terminal_actual,
        foto_url=foto_url
    )

    # Actualizar código de cámara si cambió número interno
    cam = db.query(CamaraVehiculo).filter(CamaraVehiculo.vehiculo_id == vehiculo_id).first()
    if cam:
        cam.codigo_camara = f"CAM-{numero_interno.strip().upper()}"
        db.commit()

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
    departamentos = ["La Paz", "Cochabamba", "Santa Cruz", "Oruro", "Potosí", "Chuquisaca", "Tarija", "Beni", "Pando"]
    return templates.TemplateResponse(
        request=request,
        name="usuarios.html",
        context={
            "current_user": current_user,
            "usuarios": usuarios,
            "departamentos": departamentos,
            "terminales_por_ciudad": TERMINALES_POR_CIUDAD,
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
    telefono: Optional[str] = Form(None),
    tipo_sangre: Optional[str] = Form(None),
    departamento: Optional[str] = Form(None),
    terminal_asignada: Optional[str] = Form(None),
    licencia_conducir: Optional[str] = Form(None),
    categoria_licencia: Optional[str] = Form(None),
    contacto_emergencia_nombre: Optional[str] = Form(None),
    telefono_emergencia: Optional[str] = Form(None),
    foto: Optional[UploadFile] = File(None),
    current_user: Usuario = Depends(require_roles([RolUsuario.ADMIN])),
    db: Session = Depends(get_db)
):
    import re
    from app.models.models import Rol
    from app.core.security import get_password_hash

    # Validar nombre y apellido: estrictamente sin números
    if not re.match(r"^[A-Za-zÁÉÍÓÚáéíóúñÑüÜ\s'-]{2,100}$", nombre.strip()):
        return RedirectResponse(url="/usuarios?error=El+nombre+solo+debe+contener+letras+y+espacios", status_code=status.HTTP_303_SEE_OTHER)
    if not re.match(r"^[A-Za-zÁÉÍÓÚáéíóúñÑüÜ\s'-]{2,100}$", apellido.strip()):
        return RedirectResponse(url="/usuarios?error=El+apellido+solo+debe+contener+letras+y+espacios", status_code=status.HTTP_303_SEE_OTHER)

    # Validar CI
    if not re.match(r"^[0-9]{4,10}(-[0-9A-Za-z]{1,2})?$", ci.strip()):
        return RedirectResponse(url="/usuarios?error=El+CI+debe+ser+un+documento+valido", status_code=status.HTTP_303_SEE_OTHER)

    # Validar Correo
    if not re.match(r"^[\w\.-]+@[\w\.-]+\.\w+$", email.strip()):
        return RedirectResponse(url="/usuarios?error=El+correo+electronico+no+es+valido", status_code=status.HTTP_303_SEE_OTHER)

    # Validar Teléfono personal
    if telefono and telefono.strip() and not re.match(r"^[67][0-9]{7}$", telefono.strip()):
        return RedirectResponse(url="/usuarios?error=El+telefono+debe+ser+un+celular+boliviano+de+8+digitos", status_code=status.HTTP_303_SEE_OTHER)

    # Validar Tipo de Sangre
    if tipo_sangre and tipo_sangre.strip():
        if tipo_sangre.strip().upper() not in ["O+", "O-", "A+", "A-", "B+", "B-", "AB+", "AB-"]:
            return RedirectResponse(url="/usuarios?error=Tipo+de+sangre+no+valido", status_code=status.HTTP_303_SEE_OTHER)

    # Validar si el rol es conductor, debe tener licencia
    if rol == "CONDUCTOR":
        if not licencia_conducir or not categoria_licencia:
            return RedirectResponse(url="/usuarios?error=Conductor+debe+tener+licencia+y+categoria", status_code=status.HTTP_303_SEE_OTHER)
        if contacto_emergencia_nombre and contacto_emergencia_nombre.strip() and not re.match(r"^[A-Za-zÁÉÍÓÚáéíóúñÑüÜ\s'-]{2,100}$", contacto_emergencia_nombre.strip()):
            return RedirectResponse(url="/usuarios?error=El+nombre+del+contacto+de+emergencia+solo+debe+contener+letras", status_code=status.HTTP_303_SEE_OTHER)
        if telefono_emergencia and telefono_emergencia.strip() and not re.match(r"^[67][0-9]{7}$", telefono_emergencia.strip()):
            return RedirectResponse(url="/usuarios?error=El+telefono+de+emergencia+debe+tener+8+digitos", status_code=status.HTTP_303_SEE_OTHER)

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
        telefono=telefono.strip() if telefono and telefono.strip() else None,
        tipo_sangre=tipo_sangre.strip().upper() if tipo_sangre and tipo_sangre.strip() else None,
        departamento=departamento.strip() if departamento and departamento.strip() else "Cochabamba",
        terminal_asignada=terminal_asignada.strip() if terminal_asignada and terminal_asignada.strip() else None,
        estado=True
    )
    db.add(nuevo_user)
    db.flush()

    if rol == "CONDUCTOR":
        nuevo_conductor = Conductor(
            id=nuevo_user.id,
            licencia_conducir=licencia_conducir.strip(),
            categoria_licencia=categoria_licencia.strip(),
            contacto_emergencia_nombre=contacto_emergencia_nombre.strip() if contacto_emergencia_nombre and contacto_emergencia_nombre.strip() else None,
            telefono_emergencia=telefono_emergencia.strip() if telefono_emergencia and telefono_emergencia.strip() else None,
            puntaje_promedio=0.00,
            viajes_concluidos=0,
            ubicacion_actual=departamento.strip() if departamento and departamento.strip() else "Cochabamba"
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
    telefono: Optional[str] = Form(None),
    tipo_sangre: Optional[str] = Form(None),
    departamento: Optional[str] = Form(None),
    terminal_asignada: Optional[str] = Form(None),
    estado: Optional[str] = Form(None),
    licencia_conducir: Optional[str] = Form(None),
    categoria_licencia: Optional[str] = Form(None),
    contacto_emergencia_nombre: Optional[str] = Form(None),
    telefono_emergencia: Optional[str] = Form(None),
    foto: Optional[UploadFile] = File(None),
    current_user: Usuario = Depends(require_roles([RolUsuario.ADMIN])),
    db: Session = Depends(get_db)
):
    import re
    repo = UsuarioRepository(db)
    user = repo.get_by_id(usuario_id)
    
    if not user:
        return RedirectResponse(url="/usuarios?error=Usuario+no+encontrado", status_code=status.HTTP_303_SEE_OTHER)

    if not re.match(r"^[A-Za-zÁÉÍÓÚáéíóúñÑüÜ\s'-]{2,100}$", nombre.strip()):
        return RedirectResponse(url="/usuarios?error=El+nombre+solo+debe+contener+letras+y+espacios", status_code=status.HTTP_303_SEE_OTHER)
    if not re.match(r"^[A-Za-zÁÉÍÓÚáéíóúñÑüÜ\s'-]{2,100}$", apellido.strip()):
        return RedirectResponse(url="/usuarios?error=El+apellido+solo+debe+contener+letras+y+espacios", status_code=status.HTTP_303_SEE_OTHER)
    if not re.match(r"^[0-9]{4,10}(-[0-9A-Za-z]{1,2})?$", ci.strip()):
        return RedirectResponse(url="/usuarios?error=El+CI+debe+ser+un+documento+valido", status_code=status.HTTP_303_SEE_OTHER)
    if not re.match(r"^[\w\.-]+@[\w\.-]+\.\w+$", email.strip()):
        return RedirectResponse(url="/usuarios?error=El+correo+electronico+no+es+valido", status_code=status.HTTP_303_SEE_OTHER)

    if telefono and telefono.strip() and not re.match(r"^[67][0-9]{7}$", telefono.strip()):
        return RedirectResponse(url="/usuarios?error=El+telefono+debe+ser+un+celular+boliviano+de+8+digitos", status_code=status.HTTP_303_SEE_OTHER)

    user.nombre = nombre.strip()
    user.apellido = apellido.strip()
    user.ci = ci.strip()
    user.email = email.strip().lower()
    user.telefono = telefono.strip() if telefono and telefono.strip() else None
    user.tipo_sangre = tipo_sangre.strip().upper() if tipo_sangre and tipo_sangre.strip() else None
    user.departamento = departamento.strip() if departamento and departamento.strip() else None
    user.terminal_asignada = terminal_asignada.strip() if terminal_asignada and terminal_asignada.strip() else None
    user.estado = True if estado == "on" else False

    # Subir foto si fue proporcionada
    if foto and foto.filename:
        foto_url = _save_upload(foto, "usuarios", str(usuario_id))
        if foto_url:
            user.foto_url = foto_url

    if user.rol.value == "CONDUCTOR":
        if contacto_emergencia_nombre and contacto_emergencia_nombre.strip() and not re.match(r"^[A-Za-zÁÉÍÓÚáéíóúñÑüÜ\s'-]{2,100}$", contacto_emergencia_nombre.strip()):
            return RedirectResponse(url="/usuarios?error=El+nombre+del+contacto+de+emergencia+solo+debe+contener+letras", status_code=status.HTTP_303_SEE_OTHER)
        if telefono_emergencia and telefono_emergencia.strip() and not re.match(r"^[67][0-9]{7}$", telefono_emergencia.strip()):
            return RedirectResponse(url="/usuarios?error=El+telefono+de+emergencia+debe+tener+8+digitos", status_code=status.HTTP_303_SEE_OTHER)

        if user.conductor:
            if licencia_conducir:
                user.conductor.licencia_conducir = licencia_conducir.strip()
            if categoria_licencia:
                user.conductor.categoria_licencia = categoria_licencia.strip()
            user.conductor.contacto_emergencia_nombre = contacto_emergencia_nombre.strip() if contacto_emergencia_nombre and contacto_emergencia_nombre.strip() else None
            user.conductor.telefono_emergencia = telefono_emergencia.strip() if telefono_emergencia and telefono_emergencia.strip() else None
            if departamento:
                user.conductor.ubicacion_actual = departamento.strip()
        else:
            if licencia_conducir and categoria_licencia:
                db_conductor = Conductor(
                    id=user.id,
                    licencia_conducir=licencia_conducir.strip(),
                    categoria_licencia=categoria_licencia.strip(),
                    contacto_emergencia_nombre=contacto_emergencia_nombre.strip() if contacto_emergencia_nombre and contacto_emergencia_nombre.strip() else None,
                    telefono_emergencia=telefono_emergencia.strip() if telefono_emergencia and telefono_emergencia.strip() else None,
                    puntaje_promedio=0.00,
                    viajes_concluidos=0,
                    ubicacion_actual=departamento.strip() if departamento and departamento.strip() else "Cochabamba"
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

    # Calcular próximo código correlativo HR-YYYY-XXXX
    anio_actual = date.today().year
    prefijo = f"HR-{anio_actual}-"
    max_sec = 0
    todas_hojas = despacho_repo.list_hojas()
    for h in todas_hojas:
        if h.codigo_hoja and h.codigo_hoja.startswith(prefijo):
            try:
                sec = int(h.codigo_hoja.split("-")[2])
                if sec > max_sec:
                    max_sec = sec
            except (ValueError, IndexError):
                pass
    proximo_codigo_hoja = f"{prefijo}{max_sec + 1:04d}"

    return templates.TemplateResponse(
        request=request,
        name="hojas_ruta.html",
        context={
            "current_user": current_user,
            "hojas": hojas,
            "vehiculos_disponibles": vehiculos_disponibles,
            "conductores": conductores,
            "proximo_codigo_hoja": proximo_codigo_hoja,
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
    coords_origen = (-17.4042, -66.1583)
    coords_destino = (-16.4883, -68.1408)
    if viaje_activo:
        coords_origen = get_coordenadas_terminal(viaje_activo.origen_ciudad, viaje_activo.origen_terminal)
        coords_destino = get_coordenadas_terminal(viaje_activo.destino_ciudad, viaje_activo.destino_terminal)

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
            "coords_origen": coords_origen,
            "coords_destino": coords_destino,
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

@router.post("/mi-perfil/actualizar")
def handle_actualizar_mi_perfil(
    telefono: Optional[str] = Form(None),
    contacto_emergencia_nombre: Optional[str] = Form(None),
    telefono_emergencia: Optional[str] = Form(None),
    foto: Optional[UploadFile] = File(None),
    current_user: Usuario = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    import re
    if telefono and telefono.strip():
        if not re.match(r"^[67][0-9]{7}$", telefono.strip()):
            return RedirectResponse(url="/mi-hoja?error=El+telefono+debe+ser+un+celular+boliviano+de+8+digitos", status_code=status.HTTP_303_SEE_OTHER)
        current_user.telefono = telefono.strip()

    if current_user.conductor:
        if contacto_emergencia_nombre and contacto_emergencia_nombre.strip():
            if not re.match(r"^[A-Za-zÁÉÍÓÚáéíóúñÑüÜ\s'-]{2,100}$", contacto_emergencia_nombre.strip()):
                return RedirectResponse(url="/mi-hoja?error=El+nombre+de+contacto+solo+debe+contener+letras", status_code=status.HTTP_303_SEE_OTHER)
            current_user.conductor.contacto_emergencia_nombre = contacto_emergencia_nombre.strip()

        if telefono_emergencia and telefono_emergencia.strip():
            if not re.match(r"^[67][0-9]{7}$", telefono_emergencia.strip()):
                return RedirectResponse(url="/mi-hoja?error=El+telefono+de+emergencia+debe+tener+8+digitos", status_code=status.HTTP_303_SEE_OTHER)
            current_user.conductor.telefono_emergencia = telefono_emergencia.strip()

    if foto and foto.filename:
        foto_url = _save_upload(foto, "usuarios", str(current_user.id))
        if foto_url:
            current_user.foto_url = foto_url

    db.commit()
    return RedirectResponse(url="/mi-hoja?success=Perfil+actualizado+exitosamente", status_code=status.HTTP_303_SEE_OTHER)

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
    y Protocolo de Parada Segura (PPS). Simulaciones eliminadas.
    """
    service = TelemetriaService(db)
    flota = service.obtener_flota_monitoreo()

    return templates.TemplateResponse(
        request=request,
        name="monitoreo.html",
        context={
            "current_user": current_user,
            "filtro_hoja_id": str(hoja_id) if hoja_id else None,
            "flota_inicial": flota
        }
    )

@router.get("/centro-camaras", response_class=HTMLResponse)
@router.get("/centro-camaras/", response_class=HTMLResponse)
def view_centro_camaras(
    request: Request,
    current_user: Usuario = Depends(require_roles([RolUsuario.ADMIN, RolUsuario.OPERADOR])),
    db: Session = Depends(get_db)
):
    """
    Centro de Cámaras para Admin y Operador:
    Monitorea visualmente en tiempo real todas las cabinas registradas y en tránsito.
    """
    service = TelemetriaService(db)
    flota = service.obtener_flota_monitoreo()
    camara_repo = CamaraRepository(db)
    camaras = camara_repo.list_all()

    return templates.TemplateResponse(
        request=request,
        name="centro_camaras.html",
        context={
            "current_user": current_user,
            "flota": flota,
            "camaras": camaras
        }
    )

# =========================================================
# GESTIÓN Y CRUD DE CÁMARAS (SOLO ADMINISTRADOR)
# =========================================================

@router.get("/camaras", response_class=HTMLResponse)
def view_camaras(
    request: Request,
    current_user: Usuario = Depends(require_roles([RolUsuario.ADMIN])),
    error: Optional[str] = None,
    success: Optional[str] = None,
    db: Session = Depends(get_db)
):
    repo = CamaraRepository(db)
    camaras = repo.list_all()
    vehiculos_disponibles = repo.get_vehiculos_disponibles_para_camara()
    return templates.TemplateResponse(
        request=request,
        name="camaras.html",
        context={
            "current_user": current_user,
            "camaras": camaras,
            "vehiculos_disponibles": vehiculos_disponibles,
            "error_msg": error,
            "success_msg": success
        }
    )

@router.post("/camaras/nuevo")
def handle_nueva_camara(
    vehiculo_id: UUID = Form(...),
    marca_modelo: Optional[str] = Form("Cámara Celular Cabina"),
    tipo_dispositivo: Optional[str] = Form("CELULAR_CONDUCTOR"),
    resolucion: Optional[str] = Form("640x480"),
    estado: Optional[str] = Form("ACTIVA"),
    current_user: Usuario = Depends(require_roles([RolUsuario.ADMIN])),
    db: Session = Depends(get_db)
):
    repo = CamaraRepository(db)
    flota_repo = VehiculoRepository(db)
    bus = flota_repo.get_by_id(vehiculo_id)
    if not bus:
        return RedirectResponse(url="/camaras?error=Veh%C3%ADculo+no+encontrado", status_code=status.HTTP_303_SEE_OTHER)

    codigo_camara = f"CAM-{bus.numero_interno}"

    existente_bus = repo.get_by_vehiculo_id(vehiculo_id)
    if existente_bus:
        return RedirectResponse(url="/camaras?error=Este+veh%C3%ADculo+ya+tiene+una+c%C3%A1mara+asignada", status_code=status.HTTP_303_SEE_OTHER)
    repo.create(
        vehiculo_id=vehiculo_id,
        codigo_camara=codigo_camara,
        marca_modelo=marca_modelo,
        tipo_dispositivo=tipo_dispositivo,
        resolucion=resolucion,
        estado=estado
    )
    return RedirectResponse(url="/camaras?success=C%C3%A1mara+registrada+correctamente", status_code=status.HTTP_303_SEE_OTHER)

@router.post("/camaras/{camara_id}/editar")
def handle_editar_camara(
    camara_id: UUID,
    vehiculo_id: UUID = Form(...),
    marca_modelo: Optional[str] = Form("Cámara Celular Cabina"),
    tipo_dispositivo: Optional[str] = Form("CELULAR_CONDUCTOR"),
    resolucion: Optional[str] = Form("640x480"),
    estado: Optional[str] = Form("ACTIVA"),
    current_user: Usuario = Depends(require_roles([RolUsuario.ADMIN])),
    db: Session = Depends(get_db)
):
    repo = CamaraRepository(db)
    flota_repo = VehiculoRepository(db)
    bus = flota_repo.get_by_id(vehiculo_id)
    if not bus:
        return RedirectResponse(url="/camaras?error=Veh%C3%ADculo+no+encontrado", status_code=status.HTTP_303_SEE_OTHER)

    codigo_camara = f"CAM-{bus.numero_interno}"

    existente_bus = repo.get_by_vehiculo_id(vehiculo_id)
    if existente_bus and str(existente_bus.id) != str(camara_id):
        return RedirectResponse(url="/camaras?error=Este+veh%C3%ADculo+ya+tiene+otra+c%C3%A1mara+asignada", status_code=status.HTTP_303_SEE_OTHER)

    repo.update(
        camara_id=camara_id,
        vehiculo_id=vehiculo_id,
        codigo_camara=codigo_camara,
        marca_modelo=marca_modelo,
        tipo_dispositivo=tipo_dispositivo,
        resolucion=resolucion,
        estado=estado
    )
    return RedirectResponse(url="/camaras?success=C%C3%A1mara+actualizada+correctamente", status_code=status.HTTP_303_SEE_OTHER)

@router.post("/camaras/{camara_id}/eliminar")
def handle_eliminar_camara(
    camara_id: UUID,
    current_user: Usuario = Depends(require_roles([RolUsuario.ADMIN])),
    db: Session = Depends(get_db)
):
    repo = CamaraRepository(db)
    repo.delete(camara_id)
    return RedirectResponse(url="/camaras?success=C%C3%A1mara+eliminada+correctamente", status_code=status.HTTP_303_SEE_OTHER)

@router.post("/hojas-ruta/{hoja_id}/finalizar-admin")
def handle_finalizar_hoja_admin(
    hoja_id: UUID,
    current_user: Usuario = Depends(require_roles([RolUsuario.ADMIN, RolUsuario.OPERADOR])),
    db: Session = Depends(get_db)
):
    service = DespachoService(db)
    try:
        service.finalizar_viaje(hoja_id)
        return RedirectResponse(url="/hojas-ruta?success=Viaje+finalizado+correctamente+por+administraci%C3%B3n", status_code=status.HTTP_303_SEE_OTHER)
    except HTTPException as e:
        return RedirectResponse(url=f"/hojas-ruta?error={e.detail}", status_code=status.HTTP_303_SEE_OTHER)

@router.post("/monitoreo/atender")
async def handle_atender_incidente_web(
    incidente_id: Optional[str] = Form(None),
    hoja_de_ruta_id: Optional[UUID] = Form(None),
    accion_tomada: AccionAtencion = Form(...),
    mensaje_enviado: Optional[str] = Form(None),
    audio_url: Optional[str] = Form(None),
    current_user: Usuario = Depends(require_roles([RolUsuario.ADMIN, RolUsuario.OPERADOR])),
    db: Session = Depends(get_db)
):
    """
    Procesa el formulario web del modal Protocolo de Parada Segura (PPS).
    Soporta atención de incidente existente o envío directo de instrucción/audio a cabina.
    """
    service = TelemetriaService(db)
    clean_inc_id = None
    if incidente_id and incidente_id.strip():
        try:
            clean_inc_id = UUID(incidente_id.strip())
        except ValueError:
            clean_inc_id = None

    if not clean_inc_id:
        from app.models.models import IncidenteAlerta, TipoIncidente, NivelRiesgo, HojaDeRuta
        inc = None
        if hoja_de_ruta_id:
            inc = (
                db.query(IncidenteAlerta)
                .filter(IncidenteAlerta.hoja_de_ruta_id == hoja_de_ruta_id)
                .order_by(IncidenteAlerta.timestamp_evento.desc())
                .first()
            )
        if inc:
            clean_inc_id = inc.id
        else:
            hoja = db.query(HojaDeRuta).filter(HojaDeRuta.id == hoja_de_ruta_id).first() if hoja_de_ruta_id else None
            cond_id = hoja.tripulacion[0].conductor_id if (hoja and hoja.tripulacion) else None
            nuevo_inc = IncidenteAlerta(
                hoja_de_ruta_id=hoja_de_ruta_id,
                conductor_id=cond_id,
                tipo_incidente=TipoIncidente.SOMNOLENCIA_PREVENTIVA,
                velocidad_instantanea=0.0,
                latitud=-17.4042,
                longitud=-66.1583,
                nivel_riesgo=NivelRiesgo.AMARILLO,
                alarma_disparada=False
            )
            db.add(nuevo_inc)
            db.commit()
            db.refresh(nuevo_inc)
            clean_inc_id = nuevo_inc.id

    try:
        await service.atender_incidente(
            AtencionIncidenteCreate(
                incidente_id=clean_inc_id,
                accion_tomada=accion_tomada,
                mensaje_enviado=mensaje_enviado.strip() if mensaje_enviado else None,
                audio_url=audio_url.strip() if audio_url else None
            ),
            operador_actual=current_user
        )
        if "application/json" in request.headers.get("accept", ""):
            from fastapi.responses import JSONResponse
            return JSONResponse({"status": "OK", "mensaje": "Instrucción y audio enviados correctamente a la cabina"})

        return RedirectResponse(
            url="/monitoreo?success=Instrucci%C3%B3n+y+audio+enviados+correctamente+a+la+cabina",
            status_code=status.HTTP_303_SEE_OTHER
        )
    except HTTPException as e:
        if "application/json" in request.headers.get("accept", ""):
            from fastapi.responses import JSONResponse
            return JSONResponse({"status": "ERROR", "detail": str(e.detail)}, status_code=e.status_code)

        return RedirectResponse(
            url=f"/monitoreo?error={e.detail}",
            status_code=status.HTTP_303_SEE_OTHER
        )

# =========================================================
# VISTA DE REPORTES DINÁMICOS Y AUDITORÍA
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
    Vista de Reportes Dinámicos generados a partir de datos de simulación/telemetría
    con analítica gerencial y reconstrucción/estimación numérica de fatiga.
    """
    from sqlalchemy.orm import joinedload
    from app.services.metodos_numericos import (
        calcular_diferencias_adelante,
        interpolar_newton_adelante,
        interpolar_newton_atras,
        interpolar_lineal
    )

    # 1. Resumen de Viajes (Últimos 50)
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
    resumen_viajes = []
    for h in hojas:
        n_tele = db.query(func.count(RegistroTelemetria.id)).filter(
            RegistroTelemetria.hoja_de_ruta_id == h.id
        ).scalar() or 0
        n_inc = db.query(func.count(IncidenteAlerta.id)).filter(
            IncidenteAlerta.hoja_de_ruta_id == h.id
        ).scalar() or 0
        resumen_viajes.append({
            "hoja": h,
            "total_telemetrias": n_tele,
            "total_incidentes": n_inc
        })

    # 2. Resumen de Incidentes (Últimos 100)
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

    # 3. Resumen de Fatiga por Conductor (Cálculo directo y seguro)
    conductores = db.query(Conductor).options(joinedload(Conductor.usuario)).all()
    resumen_fatiga = []
    for c in conductores:
        if not c.usuario:
            continue
        # Filtrar incidentes de este conductor
        incs_cond = [i for i in incidentes if i.conductor_id == c.id]
        total_inc = len(incs_cond)
        fatiga_critica = sum(1 for i in incs_cond if i.tipo_incidente and i.tipo_incidente.value == "FATIGA_CRITICA")
        somnolencia = sum(1 for i in incs_cond if i.tipo_incidente and i.tipo_incidente.value == "SOMNOLENCIA_PREVENTIVA")
        exceso_vel = sum(1 for i in incs_cond if i.tipo_incidente and i.tipo_incidente.value == "EXCESO_VELOCIDAD")

        ifs = [float(i.indice_fatiga_if) for i in incs_cond if i.indice_fatiga_if is not None]
        promedio_if = round(sum(ifs) / len(ifs), 3) if ifs else 0.120
        max_if = round(max(ifs), 3) if ifs else 0.250

        perclos_list = [float(i.perclos_porcentaje) for i in incs_cond if i.perclos_porcentaje is not None]
        promedio_perclos = round(sum(perclos_list) / len(perclos_list), 2) if perclos_list else 10.5

        resumen_fatiga.append({
            "conductor": c,
            "total_incidentes": total_inc,
            "promedio_if": promedio_if,
            "max_if": max_if,
            "promedio_perclos": promedio_perclos,
            "fatiga_critica": fatiga_critica,
            "somnolencia": somnolencia,
            "exceso_vel": exceso_vel
        })

    # 4. KPIs Gerenciales
    total_viajes = db.query(func.count(HojaDeRuta.id)).scalar() or len(hojas)
    total_incidentes = len(incidentes)
    total_criticos = sum(1 for i in incidentes if i.tipo_incidente and i.tipo_incidente.value == "FATIGA_CRITICA")
    tasa_critica = round((total_criticos / total_incidentes * 100) if total_incidentes > 0 else 0, 1)
    total_atendidos = sum(1 for i in incidentes if i.atencion)
    eficacia_pps = round((total_atendidos / total_incidentes * 100) if total_incidentes > 0 else 100.0, 1)
    avg_score = db.query(func.avg(Conductor.puntaje_promedio)).scalar()
    puntaje_promedio_flota = round(float(avg_score if avg_score is not None else 4.88), 2)

    # 5. Gráfico 1: Incidentes por Ruta Interdepartamental (Barras)
    rutas_map = {}
    for inc in incidentes:
        if inc.hoja_de_ruta:
            r_nombre = f"{inc.hoja_de_ruta.origen_ciudad} - {inc.hoja_de_ruta.destino_ciudad}"
            if r_nombre not in rutas_map:
                rutas_map[r_nombre] = {"ruta": r_nombre, "critico": 0, "somnolencia": 0, "velocidad": 0}
            if inc.tipo_incidente.value == "FATIGA_CRITICA":
                rutas_map[r_nombre]["critico"] += 1
            elif inc.tipo_incidente.value == "SOMNOLENCIA_PREVENTIVA":
                rutas_map[r_nombre]["somnolencia"] += 1
            elif inc.tipo_incidente.value == "EXCESO_VELOCIDAD":
                rutas_map[r_nombre]["velocidad"] += 1

    chart_rutas = list(rutas_map.values())
    if not chart_rutas:
        chart_rutas = [
            {"ruta": "Cochabamba - Santa Cruz", "critico": 4, "somnolencia": 8, "velocidad": 2},
            {"ruta": "La Paz - Oruro", "critico": 1, "somnolencia": 4, "velocidad": 3},
            {"ruta": "Cochabamba - La Paz", "critico": 3, "somnolencia": 6, "velocidad": 1},
            {"ruta": "Potosí - Sucre", "critico": 0, "somnolencia": 2, "velocidad": 1},
            {"ruta": "Santa Cruz - Tarija", "critico": 2, "somnolencia": 5, "velocidad": 0}
        ]

    # 6. Gráfico 2: Nivel de Riesgo Operativo (Dona)
    n_rojo = sum(1 for i in incidentes if i.nivel_riesgo and i.nivel_riesgo.value == "ROJO")
    n_amarillo = sum(1 for i in incidentes if i.nivel_riesgo and i.nivel_riesgo.value == "AMARILLO")
    n_verde = sum(1 for i in incidentes if i.nivel_riesgo and i.nivel_riesgo.value == "VERDE")
    if n_rojo == 0 and n_amarillo == 0 and n_verde == 0:
        n_rojo, n_amarillo, n_verde = 5, 12, 28
    chart_riesgo = {"rojo": n_rojo, "amarillo": n_amarillo, "verde": n_verde}

    # 7. Gráfico 3: Curva Horaria de Fatiga (Línea)
    horas_count = [0] * 24
    for inc in incidentes:
        if inc.timestamp_evento:
            horas_count[inc.timestamp_evento.hour] += 1
    if sum(horas_count) == 0:
        horas_count = [1, 2, 5, 8, 7, 4, 1, 0, 0, 1, 1, 2, 2, 4, 5, 3, 1, 1, 2, 2, 3, 3, 2, 1]
    chart_horario = horas_count

    # 8. Gráfico 4: Ranking de Conductores (Serializable para tojson)
    ranking_top = []
    conductores_ordenados = sorted(resumen_fatiga, key=lambda x: (x["conductor"].puntaje_promedio or 0.0), reverse=True)[:5]
    for c_dict in conductores_ordenados:
        c = c_dict["conductor"]
        u = c.usuario
        ranking_top.append({
            "nombre_completo": f"{u.nombre} {u.apellido}" if u else "Conductor",
            "licencia": c.licencia_conducir or "N/R",
            "puntaje": float(c.puntaje_promedio or 4.5),
            "total_incidentes": c_dict["total_incidentes"]
        })

    # 9. Datos base para el Laboratorio de Estimación y Reconstrucción de Telemetría
    telemetria_muestra = [
        {"minuto": 0, "if_valor": 0.10, "perclos": 8.5},
        {"minuto": 15, "if_valor": 0.18, "perclos": 14.0},
        {"minuto": 30, "if_valor": 0.32, "perclos": 25.0},
        {"minuto": 45, "if_valor": 0.48, "perclos": 38.0},
        {"minuto": 60, "if_valor": 0.72, "perclos": 58.0},
        {"minuto": 75, "if_valor": 0.81, "perclos": 66.0},
        {"minuto": 90, "if_valor": 0.60, "perclos": 48.0}
    ]

    return templates.TemplateResponse(
        request=request,
        name="reportes.html",
        context={
            "current_user": current_user,
            "resumen_viajes": resumen_viajes,
            "resumen_incidentes": resumen_incidentes,
            "resumen_fatiga": resumen_fatiga,
            "kpis": {
                "total_viajes": total_viajes,
                "total_incidentes": total_incidentes,
                "total_criticos": total_criticos,
                "tasa_critica": tasa_critica,
                "total_atendidos": total_atendidos,
                "eficacia_pps": eficacia_pps,
                "puntaje_promedio_flota": puntaje_promedio_flota
            },
            "chart_rutas": chart_rutas,
            "chart_riesgo": chart_riesgo,
            "chart_horario": chart_horario,
            "ranking_top": ranking_top,
            "telemetria_muestra": telemetria_muestra,
            "tipo_reporte": tipo,
            "now": datetime.now()
        }
    )

@router.post("/api/reportes/interpolar")
def api_interpolar_telemetria(
    request: Request,
    payload: dict,
    current_user: Usuario = Depends(require_roles([RolUsuario.ADMIN, RolUsuario.OPERADOR]))
):
    """
    Endpoint para evaluar interpolación matemática (Newton adelante/atrás o Lineal)
    sobre puntos temporales de telemetría de fatiga.
    """
    from fastapi.responses import JSONResponse
    from app.services.metodos_numericos import (
        interpolar_newton_adelante,
        interpolar_newton_atras,
        interpolar_lineal
    )

    metodo = payload.get("metodo", "newton_adelante")
    x = [float(val) for val in payload.get("x", [])]
    y = [float(val) for val in payload.get("y", [])]
    t = float(payload.get("t", 0.0))

    if len(x) < 2 or len(y) < 2 or len(x) != len(y):
        return JSONResponse({"status": "ERROR", "detail": "Datos insuficientes o inconsistentes para interpolar."}, status_code=400)

    if metodo == "newton_adelante":
        res = interpolar_newton_adelante(x, y, t)
    elif metodo == "newton_atras":
        res = interpolar_newton_atras(x, y, t)
    elif metodo == "lineal":
        res = interpolar_lineal(x, y, t)
    else:
        return JSONResponse({"status": "ERROR", "detail": "Método no reconocido."}, status_code=400)

    return JSONResponse({"status": "OK", "data": res})

