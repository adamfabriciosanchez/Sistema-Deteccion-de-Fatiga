import os
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from app.core.config import settings
from app.routers import auth_router, views_router, flota_router, despacho_router, telemetria_router

app = FastAPI(
    title=settings.PROJECT_NAME,
    version=settings.VERSION,
    description="Plataforma de gestión de flota, pre-despacho y monitoreo geoespacial para Trans Copacabana."
)

# Configuración de CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Servir archivos estáticos (CSS, JS, iconos)
static_dir = os.path.join(os.path.dirname(__file__), "app", "static")
if not os.path.exists(static_dir):
    os.makedirs(static_dir, exist_ok=True)
app.mount("/static", StaticFiles(directory=static_dir), name="static")

# Inclusión de Rutas de Vistas Web (Jinja2)
app.include_router(views_router.router)

# Inclusión de Routers de la API REST (/api/v1)
app.include_router(auth_router.router, prefix=settings.API_V1_STR)
app.include_router(flota_router.router, prefix=settings.API_V1_STR)
app.include_router(despacho_router.router, prefix=settings.API_V1_STR)

# Inclusión del Router de Telemetría (WebSockets y REST)
app.include_router(telemetria_router.router)

@app.get("/health", tags=["Estado del Sistema"])
def health_check():
    """Endpoint para monitoreo de salud del servidor."""
    return {"status": "ok", "app": settings.PROJECT_NAME, "version": settings.VERSION}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True)
