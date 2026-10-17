from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base
from app.core.config import settings

# Engine de SQLAlchemy con pooling configurado para rendimiento
engine = create_engine(
    settings.DATABASE_URL,
    pool_pre_ping=True,
    pool_size=10,
    max_overflow=20
)

# Creador de sesiones
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Base declarativa para modelos ORM
Base = declarative_base()

def get_db():
    """
    Generador de dependencias FastAPI para obtener sesiones de base de datos.
    Cierra la sesión automáticamente al finalizar la solicitud.
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
