from typing import Optional, Dict, Any
from sqlalchemy.orm import Session
from app.repositories.usuario_repo import UsuarioRepository
from app.core.security import verify_password, create_access_token
from app.models.models import Usuario

class AuthService:
    def __init__(self, db: Session):
        self.repo = UsuarioRepository(db)

    def authenticate(self, email: str, password: str) -> Optional[Usuario]:
        user = self.repo.get_by_email(email)
        if not user:
            return None
        if not user.estado:
            return None
        if not verify_password(password, user.password_hash):
            return None
        return user

    def generate_token_data(self, user: Usuario) -> Dict[str, Any]:
        token_payload = {
            "sub": str(user.id),
            "email": user.email,
            "rol": user.rol.value,
            "nombre": f"{user.nombre} {user.apellido}"
        }
        token = create_access_token(data=token_payload)
        return {
            "access_token": token,
            "token_type": "bearer",
            "rol": user.rol,
            "nombre_completo": f"{user.nombre} {user.apellido}"
        }
