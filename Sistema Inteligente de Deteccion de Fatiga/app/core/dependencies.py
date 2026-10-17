from typing import Optional, List
from uuid import UUID
from fastapi import Depends, HTTPException, status, Request
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.core.security import decode_access_token
from app.repositories.usuario_repo import UsuarioRepository
from app.models.models import Usuario, RolUsuario

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login", auto_error=False)

def get_token_from_request(request: Request, bearer_token: Optional[str] = Depends(oauth2_scheme)) -> Optional[str]:
    """
    Obtiene el token JWT desde el encabezado Authorization (Bearer) o desde la cookie 'access_token'.
    Esto permite soportar simultáneamente clientes API REST y navegación en navegador web.
    """
    if bearer_token:
        return bearer_token
    # Buscar en cookies
    cookie_token = request.cookies.get("access_token")
    if cookie_token:
        if cookie_token.startswith("Bearer "):
            return cookie_token.replace("Bearer ", "")
        return cookie_token
    return None

def get_current_user_optional(
    request: Request,
    token: Optional[str] = Depends(get_token_from_request),
    db: Session = Depends(get_db)
) -> Optional[Usuario]:
    """
    Retorna el usuario autenticado si existe un token válido; si no, retorna None sin lanzar excepción.
    """
    if not token:
        return None
    payload = decode_access_token(token)
    if not payload:
        return None
    user_id_str = payload.get("sub")
    if not user_id_str:
        return None
    try:
        user_id = UUID(user_id_str)
    except ValueError:
        return None
    
    repo = UsuarioRepository(db)
    user = repo.get_by_id(user_id)
    if not user or not user.estado:
        return None
    return user

def get_current_user(
    user: Optional[Usuario] = Depends(get_current_user_optional)
) -> Usuario:
    """
    Exige autenticación obligatoria. Lanza HTTP 401 si no hay usuario autenticado.
    """
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Credenciales de autenticación no válidas o expiradas",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return user

def require_roles(allowed_roles: List[RolUsuario]):
    """
    Generador de dependencias para Control de Acceso Basado en Roles (RBAC).
    Lanza HTTP 403 FORBIDDEN si el usuario no cuenta con el rol requerido.
    """
    def role_checker(current_user: Usuario = Depends(get_current_user)) -> Usuario:
        if current_user.rol not in allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Acceso denegado: El rol '{current_user.rol.value}' no tiene los permisos suficientes."
            )
        return current_user
    return role_checker
