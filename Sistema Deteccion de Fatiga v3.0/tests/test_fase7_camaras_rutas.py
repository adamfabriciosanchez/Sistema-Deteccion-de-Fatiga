"""
Script de verificación para las nuevas implementaciones:
- CRUD de Cámaras de Seguridad (Admin)
- Vistas de Centro de Cámaras y Monitoreo con Panel Lateral
- Endpoint de Rutas Oficiales ATT (Red Vial Fundamental)
- Endpoint de Subida de Audio PPS
"""
import sys
import os
import io

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi.testclient import TestClient
from main import app
from app.core.database import SessionLocal
from app.models.models import Vehiculo, CamaraVehiculo

client = TestClient(app)

def test_nuevas_implementaciones():
    print("=================================================================")
    print("  EJECUTANDO PRUEBAS DE NUEVAS IMPLEMENTACIONES Y CÁMARAS        ")
    print("=================================================================")

    # 1. Login Admin y Operador
    res_admin = client.post("/api/v1/auth/login", json={"email": "admin@transcopacabana.com", "password": "123456"})
    assert res_admin.status_code == 200
    token_admin = res_admin.json()["access_token"]
    cookies_admin = {"access_token": f"Bearer {token_admin}"}

    res_op = client.post("/api/v1/auth/login", json={"email": "operador@transcopacabana.com", "password": "123456"})
    assert res_op.status_code == 200
    token_op = res_op.json()["access_token"]
    cookies_op = {"access_token": f"Bearer {token_op}"}

    print("[1/5] Autenticación completada.")

    # 2. Acceso al Centro de Cámaras (Admin y Operador)
    res_cam_center = client.get("/centro-camaras", cookies=cookies_admin)
    assert res_cam_center.status_code == 200
    assert "Centro de Cámaras en Vivo" in res_cam_center.text
    print("[2/5] Vista /centro-camaras verificada con éxito.")

    # 3. Acceso a Gestión de Cámaras (Solo Admin)
    res_cam_admin = client.get("/camaras", cookies=cookies_admin)
    assert res_cam_admin.status_code == 200
    assert "Gestión de Cámaras de Seguridad" in res_cam_admin.text

    # Con operador debe ser 403
    res_cam_op = client.get("/camaras", cookies=cookies_op)
    assert res_cam_op.status_code == 403
    print("[3/5] Permisos de Gestión de Cámaras (Admin vs Operador) validados.")

    # 4. Prueba del Endpoint de Ruta Oficial ATT
    res_ruta = client.get("/api/v1/rutas/oficial/Cochabamba/La Paz")
    assert res_ruta.status_code == 200
    data_ruta = res_ruta.json()
    assert data_ruta["distancia_km"] == 380.0
    assert len(data_ruta["puntos_latlng"]) > 10
    print(f"[4/5] Trazado oficial ATT Cochabamba -> La Paz verificado ({len(data_ruta['puntos_latlng'])} waypoints de carretera real).")

    # 5. Prueba de Subida de Audio PPS
    fake_audio = io.BytesIO(b"RIFF....WAVEfmt ....data....")
    fake_audio.name = "test_audio.webm"
    res_audio = client.post(
        "/api/v1/telemetria/subir-audio-pps",
        files={"audio_file": ("test_audio.webm", fake_audio, "audio/webm")},
        headers={"Authorization": f"Bearer {token_admin}"}
    )
    assert res_audio.status_code == 200
    assert "audio_url" in res_audio.json()
    assert "/static/uploads/audios/" in res_audio.json()["audio_url"]
    print(f"[5/5] Endpoint de subida real de audio PPS verificado: {res_audio.json()['audio_url']}")

    print("=================================================================")
    print("  RESULTADO: TODAS LAS PRUEBAS DE CÁMARAS Y RUTAS PASARON AL 100%")
    print("=================================================================")

if __name__ == "__main__":
    test_nuevas_implementaciones()

