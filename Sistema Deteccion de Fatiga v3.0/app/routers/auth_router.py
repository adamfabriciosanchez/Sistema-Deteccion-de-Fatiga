from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.core.dependencies import get_current_user
from app.schemas.usuario_schema import LoginRequest, TokenResponse, UsuarioOut
from app.services.auth_service import AuthService
from app.models.models import Usuario

router = APIRouter(prefix="/auth", tags=["Autenticación"])

@router.post("/login", response_model=TokenResponse, summary="Iniciar sesión y obtener Bearer Token")
def login(login_data: LoginRequest, db: Session = Depends(get_db)):
    """
    Endpoint para autenticación de usuarios (Admin, Operador, Conductor).
    Retorna el Bearer JWT con el rol y los datos del usuario.
    """
    service = AuthService(db)
    user = service.authenticate(login_data.email, login_data.password)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Correo electrónico o contraseña incorrectos",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return service.generate_token_data(user)

@router.get("/me", response_model=UsuarioOut, summary="Obtener perfil del usuario autenticado")
def get_current_user_profile(current_user: Usuario = Depends(get_current_user)):
    """
    Retorna la información del usuario autenticado actual.
    """
    return current_user
