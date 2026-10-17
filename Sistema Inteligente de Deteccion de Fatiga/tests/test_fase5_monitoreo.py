"""
Script de verificación integral para la Fase 5: Centro de Monitoreo (Leaflet.js) y Protocolo de Parada Segura (PPS)
"""
import sys
import os
from datetime import datetime

# Asegurar que el path del proyecto esté disponible
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi.testclient import TestClient
from main import app
from app.core.database import SessionLocal
from app.models.models import (
    HojaDeRuta,
    IncidenteAlerta,
    AtencionIncidente,
    TipoIncidente,
    NivelRiesgo,
    AccionAtencion,
    Vehiculo,
    Conductor,
    AsignacionTripulacion,
    TipoConductor,
    EstadoHoja,
    EstadoVehiculo
)
from datetime import timedelta

client = TestClient(app)

def limpiar_datos_fase5():
    db = SessionLocal()
    try:
        hojas = db.query(HojaDeRuta).filter(HojaDeRuta.codigo_hoja == "TEST-MON-01").all()
        for h in hojas:
            incs = db.query(IncidenteAlerta).filter(IncidenteAlerta.hoja_de_ruta_id == h.id).all()
            for inc in incs:
                db.query(AtencionIncidente).filter(AtencionIncidente.incidente_id == inc.id).delete()
                db.delete(inc)
            db.delete(h)
        db.query(Vehiculo).update({"estado": EstadoVehiculo.DISPONIBLE})
        db.commit()
    finally:
        db.close()

def test_fase5():
    print("=================================================================")
    print("  EJECUTANDO PRUEBAS DE LA FASE 5: MONITOREO Y PARADA SEGURA     ")
    print("=================================================================")

    limpiar_datos_fase5()

    try:
        # 1. Autenticar usuarios
        print("\n[1/5] Autenticando usuarios de prueba...")
        res_admin = client.post("/api/v1/auth/login", json={"email": "admin@transcopacabana.com", "password": "123456"})
        assert res_admin.status_code == 200, f"Error login admin: {res_admin.text}"
        token_admin = res_admin.json()["access_token"]

        res_op = client.post("/api/v1/auth/login", json={"email": "operador@transcopacabana.com", "password": "123456"})
        assert res_op.status_code == 200, f"Error login operador: {res_op.text}"
        token_operador = res_op.json()["access_token"]

        res_cond = client.post("/api/v1/auth/login", json={"email": "carlos@conductor.com", "password": "123456"})
        assert res_cond.status_code == 200, f"Error login conductor: {res_cond.text}"
        token_conductor = res_cond.json()["access_token"]
        print(" -> Autenticación de Admin, Operador y Conductor exitosa.")

        # 2. Control de Acceso a la vista de Monitoreo (/monitoreo)
        print("\n[2/5] Probando permisos de acceso a la vista /monitoreo...")
        # Conductor intentando ingresar -> 403 Forbidden
        res_cond_view = client.get("/monitoreo", headers={"Authorization": f"Bearer {token_conductor}"})
        assert res_cond_view.status_code == 403
        print(" -> Acceso denegado (HTTP 403) a Conductor en /monitoreo.")

        # Operador accediendo -> 200 OK
        res_op_view = client.get("/monitoreo", headers={"Authorization": f"Bearer {token_operador}"})
        assert res_op_view.status_code == 200
        assert "mapContainer" in res_op_view.text
        assert "Protocolo de Parada Segura" in res_op_view.text
        print(" -> Vista /monitoreo renderizada exitosamente con Leaflet y PPS para Operador.")

        # Crear hoja de ruta de prueba dedicada TEST-MON-01
        db = SessionLocal()
        bus = db.query(Vehiculo).first()
        cond = db.query(Conductor).first()
        hoja = HojaDeRuta(
            codigo_hoja="TEST-MON-01",
            vehiculo_id=bus.id,
            origen_ciudad="La Paz",
            origen_terminal="Terminal de Buses La Paz",
            destino_ciudad="Cochabamba",
            destino_terminal="Terminal de Buses Cochabamba",
            duracion_estimada_hrs=7.5,
            fecha_salida=datetime.utcnow(),
            fecha_llegada_estimada=datetime.utcnow() + timedelta(hours=7, minutes=30),
            estado=EstadoHoja.EN_TRANSITO
        )
        db.add(hoja)
        db.flush()
        db.add(AsignacionTripulacion(
            hoja_de_ruta_id=hoja.id,
            conductor_id=cond.id,
            tipo_conductor=TipoConductor.PRINCIPAL
        ))
        db.commit()
        db.refresh(hoja)

        conductor_id = cond.id
        hoja_id = hoja.id

        # 3. Consultar incidentes activos vía REST
        print("\n[3/5] Consultando incidentes activos vía API REST (/api/v1/incidentes/activos)...")
        res_inc = client.get("/api/v1/incidentes/activos", headers={"Authorization": f"Bearer {token_operador}"})
        assert res_inc.status_code == 200
        incidentes = res_inc.json()
        print(f" -> Incidentes registrados en el sistema: {len(incidentes)}")

        # 4. Registrar un incidente y probar Protocolo de Parada Segura (PPS)
        print("\n[4/5] Probando registro de atención PPS (POST /api/v1/incidentes/atencion)...")
        nuevo_inc = IncidenteAlerta(
            hoja_de_ruta_id=hoja_id,
            conductor_id=conductor_id,
            tipo_incidente=TipoIncidente.EXCESO_VELOCIDAD,
            velocidad_instantanea=92.5,
            latitud=-17.2500,
            longitud=-67.1000,
            nivel_riesgo=NivelRiesgo.AMARILLO,
            alarma_disparada=True,
            timestamp_evento=datetime.utcnow()
        )
        db.add(nuevo_inc)
        db.commit()
        db.refresh(nuevo_inc)
        inc_id = str(nuevo_inc.id)
        db.close()

        # Operador atiende el incidente aplicando PPS (mensaje_enviado, audio_url)
        res_atencion = client.post(
            "/api/v1/incidentes/atencion",
            headers={"Authorization": f"Bearer {token_operador}"},
            json={
                "incidente_id": inc_id,
                "accion_tomada": "ORDEN_DESCANSO",
                "mensaje_enviado": "Se ordenó detención de 20 minutos en parador seguro y relevo de chofer.",
                "audio_url": "https://storage.transcopacabana.com/audios/orden_descanso_104.mp3"
            }
        )
        assert res_atencion.status_code == 201, f"Error: {res_atencion.text}"
        atencion_data = res_atencion.json()
        assert atencion_data["accion_tomada"] == "ORDEN_DESCANSO"
        assert atencion_data["mensaje_enviado"] == "Se ordenó detención de 20 minutos en parador seguro y relevo de chofer."
        print(f" -> Atención PPS registrada con éxito: {atencion_data['accion_tomada']} | Mensaje: {atencion_data['mensaje_enviado']}")

        # 5. Validar que no se pueda atender dos veces el mismo incidente
        print("\n[5/5] Validando bloqueo de duplicidad en atención de incidentes...")
        res_atencion_dup = client.post(
            "/api/v1/incidentes/atencion",
            headers={"Authorization": f"Bearer {token_operador}"},
            json={
                "incidente_id": inc_id,
                "accion_tomada": "LLAMADA_VERIFICACION",
                "mensaje_enviado": "Intento de segunda atención"
            }
        )
        assert res_atencion_dup.status_code == 400
        assert "ya fue atendido" in res_atencion_dup.json()["detail"]
        print(" -> Bloqueo HTTP 400 validado: Incidente cerrado no puede duplicar atención.")

        print("\n=================================================================")
        print("  RESULTADO: TODAS LAS PRUEBAS DE LA FASE 5 PASARON CON ÉXITO    ")
        print("=================================================================")
    finally:
        limpiar_datos_fase5()

if __name__ == "__main__":
    test_fase5()
