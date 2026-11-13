"""
===============================================================================
SUITE DE PRUEBAS INTEGRALES END-TO-END (E2E) - TRANS COPACABANA (3FN)
===============================================================================
Valida el ciclo de vida completo de una operación de transporte interdepartamental:
1. Autenticación y RBAC (Admin, Operador, Conductor).
2. Registro de bus en flota (1FN / numero_interno).
3. Programación de Hoja de Ruta con Regla ATT de Tripulación Doble (>4.0 hrs).
4. Estación de Pre-despacho en Terminal (Control estricto de Alcotest 0.00 mg/L).
5. Inicio de Tránsito a carretera.
6. Transmisión y recepción de telemetría GPS vía WebSockets (/ws/telemetry y /ws/dashboard).
7. Detección automática de exceso de velocidad y emisión de alerta en tiempo real.
8. Aplicación del Protocolo de Parada Segura (PPS) por el Operador (mensaje_enviado / audio_url).
9. Consulta de historial geoespacial en formato GeoJSON.
10. Finalización de viaje, actualización de ubicación y liberación de bus a DISPONIBLE.
"""

import sys
import os
import json
from datetime import datetime, timedelta

# Asegurar que el path del proyecto esté disponible
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi.testclient import TestClient
from main import app
from app.core.database import SessionLocal
from app.models.models import Conductor, Vehiculo, HojaDeRuta, EstadoHoja, EstadoVehiculo

client = TestClient(app)

def limpiar_datos_prueba_e2e():
    db = SessionLocal()
    try:
        hojas = db.query(HojaDeRuta).filter(HojaDeRuta.codigo_hoja.ilike("E2E-%")).all()
        for h in hojas:
            db.delete(h)
        buses = db.query(Vehiculo).filter(Vehiculo.numero_interno.ilike("TC-E2E-%")).all()
        for b in buses:
            db.delete(b)
        db.commit()
    finally:
        db.close()

def _ejecutar_ciclo_e2e():
    print("=================================================================")
    print("  EJECUTANDO SUITE INTEGRAL E2E: CICLO DE VIDA COMPLETO DE VIAJE ")
    print("=================================================================")

    # -------------------------------------------------------------
    # PASO 1: Autenticación de Actores del Sistema
    # -------------------------------------------------------------
    print("\n[PASO 1] Autenticando Administrador, Operador y Conductor...")
    res_admin = client.post("/api/v1/auth/login", json={"email": "admin@transcopacabana.com", "password": "123456"})
    assert res_admin.status_code == 200, f"Error auth admin: {res_admin.text}"
    token_admin = res_admin.json()["access_token"]

    res_op = client.post("/api/v1/auth/login", json={"email": "operador@transcopacabana.com", "password": "123456"})
    assert res_op.status_code == 200, f"Error auth operador: {res_op.text}"
    token_operador = res_op.json()["access_token"]

    res_cond = client.post("/api/v1/auth/login", json={"email": "carlos@conductor.com", "password": "123456"})
    assert res_cond.status_code == 200, f"Error auth conductor: {res_cond.text}"
    token_conductor = res_cond.json()["access_token"]
    print(" -> Autenticación multi-rol exitosa.")

    # -------------------------------------------------------------
    # PASO 2: Registro de Bus en Flota por el Administrador (1FN)
    # -------------------------------------------------------------
    ts_suffix = int(datetime.utcnow().timestamp()) % 10000
    interno_test = f"TC-E2E-{ts_suffix}"
    placa_test = f"77{ts_suffix % 100:02d}-XYZ"
    print(f"\n[PASO 2] Registrando nueva unidad en la flota (Interno #{interno_test}, Placa {placa_test})...")
    res_bus = client.post(
        "/api/v1/vehiculos",
        headers={"Authorization": f"Bearer {token_admin}"},
        json={
            "numero_interno": interno_test,
            "placa": placa_test,
            "modelo": "Paradiso 1800 G8 DD",
            "marca": "Scania",
            "chasis": "SC-K440",
            "carroceria": "Marcopolo G8",
            "tipo_bus": "CAMA",
            "capacidad_pasajeros": 43,
            "anio_fabricacion": 2022,
            "ubicacion_actual": "Cochabamba",
            "estado": "DISPONIBLE"
        }
    )
    assert res_bus.status_code == 201, f"Error al crear bus: {res_bus.text}"
    bus_id = res_bus.json()["id"]
    print(f" -> Bus registrado en BD (ID: {bus_id}).")

    # -------------------------------------------------------------
    # PASO 3: Programación de Hoja de Ruta aplicando Regla ATT
    # -------------------------------------------------------------
    print("\n[PASO 3] Programando Hoja de Ruta con Regla ATT de Tripulación Doble...")
    db = SessionLocal()
    conductores = db.query(Conductor).all()
    c1_id = str(conductores[0].id)
    c2_id = str(conductores[1].id)
    db.close()

    codigo_viaje = f"E2E-{int(datetime.utcnow().timestamp())}"
    res_hoja = client.post(
        "/api/v1/hojas-de-ruta",
        headers={"Authorization": f"Bearer {token_admin}"},
        json={
            "codigo_hoja": codigo_viaje,
            "vehiculo_id": bus_id,
            "origen_ciudad": "Cochabamba",
            "origen_terminal": "Terminal de Buses Cochabamba",
            "destino_ciudad": "Santa Cruz",
            "destino_terminal": "Terminal Bimodal Santa Cruz",
            "duracion_estimada_hrs": 9.5,
            "distancia_km": 480.0,
            "fecha_salida": (datetime.utcnow() + timedelta(hours=1)).isoformat(),
            "fecha_llegada_estimada": (datetime.utcnow() + timedelta(hours=10, minutes=30)).isoformat(),
            "tripulantes": [
                {"conductor_id": c1_id, "tipo_conductor": "PRINCIPAL"},
                {"conductor_id": c2_id, "tipo_conductor": "RELEVO"}
            ]
        }
    )
    assert res_hoja.status_code == 201, f"Error al programar: {res_hoja.text}"
    hoja_data = res_hoja.json()
    hoja_id = hoja_data["id"]
    assert hoja_data["estado"] == "PRE_DESPACHO"
    print(f" -> Hoja de Ruta '{codigo_viaje}' programada en estado PRE_DESPACHO con 2 conductores.")

    # -------------------------------------------------------------
    # PASO 4: Estación de Pre-Despacho (Alcotest en Terminal - Exclusivo Admin)
    # -------------------------------------------------------------
    print("\n[PASO 4] Control de alcoholemia en Terminal (Alcotest estricto 0.00 mg/L)...")
    # 4.0 Validar que Operador recibe 403 en pre-despacho
    res_alco_op_blocked = client.post(
        "/api/v1/pre-despacho",
        headers={"Authorization": f"Bearer {token_operador}"},
        json={
            "hoja_de_ruta_id": hoja_id,
            "resultado_alcotest_principal": 0.00,
            "observaciones": "Intento no autorizado"
        }
    )
    assert res_alco_op_blocked.status_code == 403
    print(" -> Bloqueo HTTP 403 comprobado: Operador no autorizado para pre-despacho.")

    # 4.1 Prueba con alcohol positivo -> Bloqueo
    res_alco_fallo = client.post(
        "/api/v1/pre-despacho",
        headers={"Authorization": f"Bearer {token_admin}"},
        json={
            "hoja_de_ruta_id": hoja_id,
            "resultado_alcotest_principal": 0.18,
            "resultado_alcotest_relevo": 0.00,
            "observaciones": "Control preliminar observado en conductor principal"
        }
    )
    assert res_alco_fallo.status_code == 201
    assert res_alco_fallo.json()["aprobado"] is False

    # 4.2 Nueva prueba con 0.00 mg/L para ambos -> Autorizado
    res_alco_ok = client.post(
        "/api/v1/pre-despacho",
        headers={"Authorization": f"Bearer {token_admin}"},
        json={
            "hoja_de_ruta_id": hoja_id,
            "resultado_alcotest_principal": 0.00,
            "resultado_alcotest_relevo": 0.00,
            "observaciones": "Ambos conductores sobrios y en condiciones óptimas."
        }
    )
    assert res_alco_ok.status_code == 201
    assert res_alco_ok.json()["aprobado"] is True

    # Verificar que el viaje pasa a AUTORIZADA
    hoja_aut = client.get(f"/api/v1/hojas-de-ruta/{hoja_id}", headers={"Authorization": f"Bearer {token_admin}"}).json()
    assert hoja_aut["estado"] == "AUTORIZADA"
    print(" -> Pre-despacho APROBADO: Hoja de ruta en estado AUTORIZADA.")

    # -------------------------------------------------------------
    # PASO 5: Confirmación de Salida a Carretera
    # -------------------------------------------------------------
    print("\n[PASO 5] Confirmando salida a carretera (Inicio de Tránsito)...")
    res_inicio = client.post(
        f"/api/v1/hojas-de-ruta/{hoja_id}/iniciar-transito",
        headers={"Authorization": f"Bearer {token_operador}"}
    )
    assert res_inicio.status_code == 200
    assert res_inicio.json()["estado"] == "EN_TRANSITO"
    print(" -> Unidad y Hoja de Ruta en estado EN_TRANSITO.")

    # -------------------------------------------------------------
    # PASO 6 y 7: Telemetría en Vivo y Alerta de Velocidad vía WebSockets
    # -------------------------------------------------------------
    print("\n[PASO 6 y 7] Transmisión GPS en vivo y disparo de alerta por velocidad...")
    incidente_id_detectado = None

    with client.websocket_connect("/ws/dashboard") as ws_dash:
        msg_init = ws_dash.receive_json()
        assert msg_init["tipo_evento"] == "SNAPSHOT_INICIAL"

        with client.websocket_connect(f"/ws/telemetry/{hoja_id}") as ws_bus:
            # Trama 1: Velocidad normal (72.0 km/h)
            ws_bus.send_text(json.dumps({
                "hoja_de_ruta_id": hoja_id,
                "conductor_id": c1_id,
                "latitud": -17.3895,
                "longitud": -66.1568,
                "velocidad_kmh": 72.0,
                "timestamp_captura": datetime.utcnow().isoformat()
            }))
            ack1 = ws_bus.receive_json()
            assert ack1["nivel_riesgo"] == "VERDE"

            dash_update = ws_dash.receive_json()
            assert dash_update["tipo_evento"] == "TELEMETRIA_ACTUALIZADA"
            assert dash_update["data"]["nivel_riesgo"] == "VERDE"
            print(" -> Telemetría normal recibida en Dashboard (72.0 km/h - Verde).")

            # Trama 2: Exceso de velocidad (93.5 km/h) -> Dispara Alerta
            ws_bus.send_text(json.dumps({
                "hoja_de_ruta_id": hoja_id,
                "conductor_id": c1_id,
                "latitud": -17.4500,
                "longitud": -65.8500,
                "velocidad_kmh": 93.5,
                "timestamp_captura": datetime.utcnow().isoformat()
            }))
            ack2 = ws_bus.receive_json()
            assert ack2["nivel_riesgo"] == "AMARILLO"

            dash_update2 = ws_dash.receive_json()
            assert dash_update2["tipo_evento"] == "TELEMETRIA_ACTUALIZADA"
            assert dash_update2["data"]["nivel_riesgo"] == "AMARILLO"

            dash_alerta = ws_dash.receive_json()
            assert dash_alerta["tipo_evento"] == "INCIDENTE_ALERTA"
            incidente_id_detectado = dash_alerta["incidente_id"]
            print(f" -> Alerta recibida en Dashboard: Exceso de velocidad (93.5 km/h - Amarillo). Incidente ID: {incidente_id_detectado}")

    # -------------------------------------------------------------
    # PASO 8: Atención con Protocolo de Parada Segura (PPS)
    # -------------------------------------------------------------
    print("\n[PASO 8] Aplicando Protocolo de Parada Segura (PPS) por el Operador...")
    assert incidente_id_detectado is not None
    res_pps = client.post(
        "/api/v1/incidentes/atencion",
        headers={"Authorization": f"Bearer {token_operador}"},
        json={
            "incidente_id": incidente_id_detectado,
            "accion_tomada": "ORDEN_DESCANSO",
            "mensaje_enviado": "Se tomó contacto con cabina. Reducir marcha a 70 km/h inmediatamente.",
            "audio_url": "https://storage.transcopacabana.com/audios/orden_descanso_e2e.mp3"
        }
    )
    assert res_pps.status_code == 201
    assert res_pps.json()["accion_tomada"] == "ORDEN_DESCANSO"
    print(" -> Incidente atendido formalmente mediante PPS y persistido en BD.")

    # -------------------------------------------------------------
    # PASO 9: Consulta de Historial GeoJSON
    # -------------------------------------------------------------
    print("\n[PASO 9] Consultando trazado del trayecto en formato GeoJSON...")
    res_geo = client.get(f"/api/v1/telemetria/historial/{hoja_id}")
    assert res_geo.status_code == 200
    geo = res_geo.json()
    assert geo["type"] == "FeatureCollection"
    assert len(geo["features"][0]["geometry"]["coordinates"]) == 2
    print(f" -> GeoJSON validado: {len(geo['features'][0]['geometry']['coordinates'])} puntos de recorrido registrados.")

    # -------------------------------------------------------------
    # PASO 10: Finalización del Viaje y Actualización de Ubicación
    # -------------------------------------------------------------
    print("\n[PASO 10] Finalizando viaje de la unidad al llegar a destino...")
    res_fin = client.post(
        f"/api/v1/hojas-de-ruta/{hoja_id}/finalizar",
        headers={"Authorization": f"Bearer {token_operador}"}
    )
    assert res_fin.status_code == 200
    assert res_fin.json()["estado"] == "FINALIZADA"

    # Verificar que el bus volvió a DISPONIBLE y actualizó su ubicación a Santa Cruz
    db = SessionLocal()
    bus_verif = db.query(Vehiculo).filter(Vehiculo.id == bus_id).first()
    assert bus_verif.estado == EstadoVehiculo.DISPONIBLE
    assert bus_verif.ubicacion_actual == "Santa Cruz"
    db.close()
    print(f" -> Hoja de Ruta FINALIZADA, Bus Interno #{interno_test} liberado a DISPONIBLE y ubicado en Santa Cruz.")

    print("\n=================================================================")
    print("  RESULTADO: EL CICLO COMPLETO E2E SE EJECUTÓ CON 100% DE ÉXITO  ")
    print("=================================================================")
def test_ciclo_completo_e2e():
    limpiar_datos_prueba_e2e()
    try:
        _ejecutar_ciclo_e2e()
    finally:
        limpiar_datos_prueba_e2e()

if __name__ == "__main__":
    test_ciclo_completo_e2e()
