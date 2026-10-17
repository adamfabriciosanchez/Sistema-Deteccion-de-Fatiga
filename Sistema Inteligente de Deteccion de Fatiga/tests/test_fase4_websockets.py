"""
Script de verificación integral para la Fase 4: WebSockets y Telemetría en Tiempo Real
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
from app.models.models import (
    HojaDeRuta,
    Vehiculo,
    Conductor,
    AsignacionTripulacion,
    RegistroTelemetria,
    IncidenteAlerta,
    TipoIncidente,
    NivelRiesgo,
    EstadoHoja,
    EstadoVehiculo,
    TipoConductor
)

client = TestClient(app)

def limpiar_datos_fase4():
    db = SessionLocal()
    try:
        hojas = db.query(HojaDeRuta).filter(HojaDeRuta.codigo_hoja == "TEST-WS-01").all()
        for h in hojas:
            db.query(IncidenteAlerta).filter(IncidenteAlerta.hoja_de_ruta_id == h.id).delete()
            db.query(RegistroTelemetria).filter(RegistroTelemetria.hoja_de_ruta_id == h.id).delete()
            db.delete(h)
        db.query(Vehiculo).update({"estado": EstadoVehiculo.DISPONIBLE})
        db.commit()
    finally:
        db.close()

def _ejecutar_fase4():
    print("=================================================================")
    print("  EJECUTANDO PRUEBAS DE LA FASE 4: WEBSOCKETS Y TELEMETRÍA       ")
    print("=================================================================")

    db = SessionLocal()
    # 1. Crear una hoja de ruta de prueba dedicada
    bus = db.query(Vehiculo).first()
    cond = db.query(Conductor).first()
    hoja = HojaDeRuta(
        codigo_hoja="TEST-WS-01",
        vehiculo_id=bus.id,
        origen_ciudad="La Paz",
        origen_terminal="Terminal de Buses La Paz",
        destino_ciudad="Cochabamba",
        destino_terminal="Terminal de Buses Cochabamba",
        duracion_estimada_hrs=7.5,
        fecha_salida=datetime.utcnow(),
        fecha_llegada_estimada=datetime.utcnow() + timedelta(hours=7, minutes=30),
        estado=EstadoHoja.AUTORIZADA
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

    hoja_id = str(hoja.id)
    conductor_id = str(hoja.tripulacion[0].conductor_id)
    codigo_hoja = hoja.codigo_hoja
    db.close()

    print(f" -> Hoja de Ruta para prueba de telemetría: {codigo_hoja} (ID: {hoja_id})")

    # 2. Conectar al WebSocket del Dashboard (/ws/dashboard)
    print("\n[1/4] Conectando al WebSocket del Dashboard de Operadores (/ws/dashboard)...")
    with client.websocket_connect("/ws/dashboard") as ws_dash:
        # 2.1 Verificar que al conectar recibe el snapshot inicial
        msg_inicial = ws_dash.receive_json()
        assert msg_inicial["tipo_evento"] == "SNAPSHOT_INICIAL"
        print(" -> Conexión exitosa a /ws/dashboard y recepción de SNAPSHOT_INICIAL confirmada.")

        # 3. Conectar al WebSocket del Bus (/ws/telemetry/{hoja_id}) y emitir telemetría normal
        print("\n[2/4] Conectando al WebSocket del Bus (/ws/telemetry/{hoja_id}) y enviando velocidad normal...")
        with client.websocket_connect(f"/ws/telemetry/{hoja_id}") as ws_bus:
            payload_normal = {
                "hoja_de_ruta_id": hoja_id,
                "conductor_id": conductor_id,
                "latitud": -16.5320,
                "longitud": -68.1755,
                "velocidad_kmh": 68.5,
                "timestamp_captura": datetime.utcnow().isoformat()
            }
            ws_bus.send_text(json.dumps(payload_normal))

            # Recibir ACK en el bus
            ack_bus = ws_bus.receive_json()
            assert ack_bus["status"] == "ACK"
            assert ack_bus["nivel_riesgo"] == "VERDE"
            print(f" -> ACK recibido en el bus: Riesgo {ack_bus['nivel_riesgo']}.")

            # Verificar que el Dashboard recibió el broadcast en tiempo real
            evento_dash = ws_dash.receive_json()
            assert evento_dash["tipo_evento"] == "TELEMETRIA_ACTUALIZADA"
            assert evento_dash["data"]["hoja_de_ruta_id"] == hoja_id
            assert evento_dash["data"]["velocidad_kmh"] == 68.5
            assert evento_dash["data"]["nivel_riesgo"] == "VERDE"
            print(" -> Evento TELEMETRIA_ACTUALIZADA recibido por broadcast en /ws/dashboard.")

            # 4. Emitir telemetría con EXCESO DE VELOCIDAD (> 80 km/h)
            print("\n[3/4] Enviando telemetría con EXCESO DE VELOCIDAD (89.0 km/h)...")
            payload_exceso = {
                "hoja_de_ruta_id": hoja_id,
                "conductor_id": conductor_id,
                "latitud": -17.2000,
                "longitud": -67.6000,
                "velocidad_kmh": 89.0,
                "timestamp_captura": datetime.utcnow().isoformat()
            }
            ws_bus.send_text(json.dumps(payload_exceso))

            # ACK en el bus con alerta amarilla
            ack_exceso = ws_bus.receive_json()
            assert ack_exceso["status"] == "ACK"
            assert ack_exceso["nivel_riesgo"] == "AMARILLO"
            assert "Exceso de velocidad" in ack_exceso["alerta"]
            print(f" -> ACK en bus con alerta: {ack_exceso['alerta']}")

            # El Dashboard debe recibir actualización de telemetría y alerta de incidente
            broadcast_tele = ws_dash.receive_json()
            assert broadcast_tele["tipo_evento"] == "TELEMETRIA_ACTUALIZADA"
            assert broadcast_tele["data"]["nivel_riesgo"] == "AMARILLO"

            broadcast_inc = ws_dash.receive_json()
            assert broadcast_inc["tipo_evento"] == "INCIDENTE_ALERTA"
            print(" -> Evento INCIDENTE_ALERTA recibido por broadcast en /ws/dashboard.")

    # 5. Verificar persistencia en base de datos PostgreSQL
    print("\n[4/4] Verificando persistencia en PostgreSQL (registro_telemetria e incidente_alerta)...")
    db = SessionLocal()
    tele_records = db.query(RegistroTelemetria).filter(RegistroTelemetria.hoja_de_ruta_id == hoja_id).all()
    assert len(tele_records) >= 2, "Deberían haberse guardado al menos 2 registros de telemetría."
    print(f" -> Registros GPS persistidos en BD: {len(tele_records)}")

    inc_records = db.query(IncidenteAlerta).filter(
        IncidenteAlerta.hoja_de_ruta_id == hoja_id,
        IncidenteAlerta.tipo_incidente == TipoIncidente.EXCESO_VELOCIDAD
    ).all()
    assert len(inc_records) >= 1, "Debería haberse registrado al menos un incidente de exceso de velocidad."
    print(f" -> Incidente de exceso de velocidad registrado en BD: {inc_records[0].velocidad_instantanea} km/h (Riesgo: {inc_records[0].nivel_riesgo.value})")

    # Probar endpoint REST de historial GeoJSON
    res_hist = client.get(f"/api/v1/telemetria/historial/{hoja_id}")
    assert res_hist.status_code == 200
    geojson_data = res_hist.json()
    assert geojson_data["type"] == "FeatureCollection"
    assert len(geojson_data["features"][0]["geometry"]["coordinates"]) >= 2
    print(f" -> Endpoint GET /api/v1/telemetria/historial/{hoja_id} retornó GeoJSON con coordenadas válidas.")

    db.close()

    print("\n=================================================================")
    print("  RESULTADO: TODAS LAS PRUEBAS DE LA FASE 4 PASARON CON ÉXITO    ")
    print("=================================================================")

def test_fase4():
    limpiar_datos_fase4()
    try:
        _ejecutar_fase4()
    finally:
        limpiar_datos_fase4()

if __name__ == "__main__":
    test_fase4()
