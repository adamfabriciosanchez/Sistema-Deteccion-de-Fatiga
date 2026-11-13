from typing import Optional, List
from uuid import UUID
from sqlalchemy.orm import Session, joinedload
from app.models.models import Usuario, Conductor, Rol, RolUsuario
from app.schemas.usuario_schema import UsuarioCreate, ConductorBase
from app.core.security import get_password_hash

class UsuarioRepository:
    def __init__(self, db: Session):
        self.db = db

    def get_by_id(self, user_id: UUID) -> Optional[Usuario]:
        return (
            self.db.query(Usuario)
            .options(joinedload(Usuario.conductor), joinedload(Usuario.rol_info))
            .filter(Usuario.id == user_id)
            .first()
        )

    def get_by_email(self, email: str) -> Optional[Usuario]:
        return (
            self.db.query(Usuario)
            .options(joinedload(Usuario.conductor), joinedload(Usuario.rol_info))
            .filter(Usuario.email == email.strip().lower())
            .first()
        )

    def get_by_ci(self, ci: str) -> Optional[Usuario]:
        return self.db.query(Usuario).filter(Usuario.ci == ci.strip()).first()

    def list_all(self, skip: int = 0, limit: int = 100) -> List[Usuario]:
        return (
            self.db.query(Usuario)
            .options(joinedload(Usuario.conductor), joinedload(Usuario.rol_info))
            .order_by(Usuario.fecha_creacion.desc())
            .offset(skip)
            .limit(limit)
            .all()
        )

    def list_conductores(self) -> List[Conductor]:
        return (
            self.db.query(Conductor)
            .options(joinedload(Conductor.usuario))
            .join(Usuario, Usuario.id == Conductor.id)
            .filter(Usuario.estado == True)
            .all()
        )

    def list_conductores_by_ubicacion(self, ciudad: str) -> List[Conductor]:
        return (
            self.db.query(Conductor)
            .options(joinedload(Conductor.usuario))
            .join(Usuario, Usuario.id == Conductor.id)
            .filter(
                Usuario.estado == True,
                Conductor.ubicacion_actual.ilike(ciudad.strip())
            )
            .all()
        )

    def get_conductor_by_id(self, conductor_id: UUID) -> Optional[Conductor]:
        return (
            self.db.query(Conductor)
            .options(joinedload(Conductor.usuario))
            .filter(Conductor.id == conductor_id)
            .first()
        )

    def get_rol_by_nombre(self, nombre: str) -> Optional[Rol]:
        return self.db.query(Rol).filter(Rol.nombre == nombre.strip().upper()).first()

    def create(self, user_in: UsuarioCreate, conductor_in: Optional[ConductorBase] = None) -> Usuario:
        rol_nombre = user_in.rol.value if hasattr(user_in.rol, "value") else str(user_in.rol)
        rol_db = self.get_rol_by_nombre(rol_nombre)
        if not rol_db:
            # Fallback a buscar por ID o crear si no existe
            rol_id = 3 if rol_nombre == "CONDUCTOR" else (2 if rol_nombre == "OPERADOR" else 1)
        else:
            rol_id = rol_db.id

        db_user = Usuario(
            ci=user_in.ci.strip(),
            nombre=user_in.nombre.strip(),
            apellido=user_in.apellido.strip(),
            email=user_in.email.strip().lower(),
            password_hash=get_password_hash(user_in.password),
            rol_id=rol_id,
            telefono=user_in.telefono.strip() if user_in.telefono else None,
            tipo_sangre=user_in.tipo_sangre.strip() if user_in.tipo_sangre else None,
            departamento=user_in.departamento.strip() if user_in.departamento else None,
            terminal_asignada=user_in.terminal_asignada.strip() if user_in.terminal_asignada else None,
            foto_url=user_in.foto_url,
            estado=user_in.estado
        )
        self.db.add(db_user)
        self.db.flush()

        if rol_nombre == "CONDUCTOR" and conductor_in:
            db_conductor = Conductor(
                id=db_user.id,
                licencia_conducir=conductor_in.licencia_conducir.strip(),
                categoria_licencia=conductor_in.categoria_licencia.strip(),
                telefono_emergencia=conductor_in.telefono_emergencia.strip() if conductor_in.telefono_emergencia else None,
                contacto_emergencia_nombre=conductor_in.contacto_emergencia_nombre.strip() if conductor_in.contacto_emergencia_nombre else None,
                puntaje_promedio=conductor_in.puntaje_promedio if conductor_in.puntaje_promedio is not None else 0.00,
                viajes_concluidos=conductor_in.viajes_concluidos or 0,
                ubicacion_actual=conductor_in.ubicacion_actual.strip() if conductor_in.ubicacion_actual else "Cochabamba"
            )
            self.db.add(db_conductor)

        self.db.commit()
        self.db.refresh(db_user)
        return self.get_by_id(db_user.id)

    def update_usuario(self, user_id: UUID, **kwargs) -> Optional[Usuario]:
        user = self.get_by_id(user_id)
        if not user:
            return None

        for key, value in kwargs.items():
            if hasattr(user, key) and value is not None:
                setattr(user, key, value)

        self.db.commit()
        self.db.refresh(user)
        return user

    def update_conductor_ubicacion(self, conductor_id: UUID, nueva_ubicacion: str) -> Optional[Conductor]:
        conductor = self.db.query(Conductor).filter(Conductor.id == conductor_id).first()
        if conductor:
            conductor.ubicacion_actual = nueva_ubicacion.strip()
            self.db.commit()
            self.db.refresh(conductor)
        return conductor

    def toggle_estado(self, user_id: UUID, nuevo_estado: bool) -> Optional[Usuario]:
        user = self.get_by_id(user_id)
        if user:
            user.estado = nuevo_estado
            self.db.commit()
            self.db.refresh(user)
        return user
