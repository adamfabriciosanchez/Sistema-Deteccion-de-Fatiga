"""
Script de verificación integral para la Fase 3: Módulo 1 (CRUDs, Regla ATT y Pre-Despacho Alcotest)
Idempotente y alineado a la arquitectura limpia 3FN.
"""
import sys
import os
from datetime import datetime, timedelta

# Asegurar que el path del proyecto está disponible
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi.testclient import TestClient
from main import app
from app.core.database import SessionLocal
from app.models.models import Vehiculo, Conductor, EstadoVehiculo, HojaDeRuta

client = TestClient(app)

def limpiar_datos_prueba():
    db = SessionLocal()
    try:
        test_codigos = ["TEST-ATT-FAIL-01", "HR-2026-VAL-01", "HR-2026-COR-01"]
        hojas = db.query(HojaDeRuta).filter(HojaDeRuta.codigo_hoja.in_(test_codigos)).all()
        for h in hojas:
            db.delete(h)
        # Asegurar que los buses de prueba queden en DISPONIBLE
        db.query(Vehiculo).filter(Vehiculo.numero_interno.in_(["TC-001", "TC-004"])).update(
            {"estado": EstadoVehiculo.DISPONIBLE}, synchronize_session=False
        )
        db.commit()
    finally:
        db.close()

def test_fase3():
    print("=================================================================")
    print("  EJECUTANDO PRUEBAS DE LA FASE 3: MÓDULO 1 (ADMIN Y DESPACHO)   ")
    print("=================================================================")

    # 0. Limpieza previa para garantizar idempotencia
    limpiar_datos_prueba()

    try:
        # 1. Obtener tokens de autenticación
        print("\n[1/6] Autenticando usuarios de prueba...")
        token_admin = client.post("/api/v1/auth/login", json={"email": "admin@transcopacabana.com", "password": "123456"}).json()["access_token"]
        token_operador = client.post("/api/v1/auth/login", json={"email": "operador@transcopacabana.com", "password": "123456"}).json()["access_token"]
        token_conductor = client.post("/api/v1/auth/login", json={"email": "carlos@conductor.com", "password": "123456"}).json()["access_token"]
        print(" -> Tokens de Admin, Operador y Conductor listos.")

        # 2. Consultar IDs de recursos semilla
        db = SessionLocal()
        bus_101 = db.query(Vehiculo).filter(Vehiculo.numero_interno == "TC-001").first()
        bus_104 = db.query(Vehiculo).filter(Vehiculo.numero_interno == "TC-004").first()
        conductores = db.query(Conductor).all()
        c1_id = str(conductores[0].id)
        c2_id = str(conductores[1].id)
        db.close()

        print(f" -> Conductores y unidades listos.")

        # 3. REGLA CRÍTICA ATT: Intento de programar viaje largo con 1 solo chofer (DEBE FALLAR)
        print("\n[2/6] Probando Regla ATT: Intento de 1 solo chofer para ruta > 4.0 hrs...")
        res_att_invalido = client.post(
            "/api/v1/hojas-de-ruta",
            headers={"Authorization": f"Bearer {token_admin}"},
            json={
                "codigo_hoja": "TEST-ATT-FAIL-01",
                "vehiculo_id": str(bus_101.id),
                "origen_ciudad": "La Paz",
                "origen_terminal": "Terminal Metropolitana",
                "destino_ciudad": "Cochabamba",
                "destino_terminal": "Terminal Bimodal",
                "duracion_estimada_hrs": 7.5,
                "fecha_salida": (datetime.utcnow() + timedelta(hours=2)).isoformat(),
                "fecha_llegada_estimada": (datetime.utcnow() + timedelta(hours=9, minutes=30)).isoformat(),
                "tripulantes": [
                    {"conductor_id": c1_id, "tipo_conductor": "PRINCIPAL"}
                ]
            }
        )
        assert res_att_invalido.status_code == 400
        assert "Regla ATT Incumplida" in res_att_invalido.json()["detail"]
        print(" -> Bloqueo exitoso (HTTP 400): Exigencia de Conductor de Relevo validada.")

        # 4. REGLA ATT: Programación válida con Tripulación Doble (Principal + Relevo)
        print("\n[3/6] Probando Regla ATT: Asignación válida de Tripulación Doble...")
        res_att_valido = client.post(
            "/api/v1/hojas-de-ruta",
            headers={"Authorization": f"Bearer {token_admin}"},
            json={
                "codigo_hoja": "HR-2026-VAL-01",
                "vehiculo_id": str(bus_101.id),
                "origen_ciudad": "La Paz",
                "origen_terminal": "Terminal Metropolitana",
                "destino_ciudad": "Cochabamba",
                "destino_terminal": "Terminal Bimodal",
                "duracion_estimada_hrs": 7.5,
                "fecha_salida": (datetime.utcnow() + timedelta(hours=2)).isoformat(),
                "fecha_llegada_estimada": (datetime.utcnow() + timedelta(hours=9, minutes=30)).isoformat(),
                "tripulantes": [
                    {"conductor_id": c1_id, "tipo_conductor": "PRINCIPAL"},
                    {"conductor_id": c2_id, "tipo_conductor": "RELEVO"}
                ]
            }
        )
        assert res_att_valido.status_code == 201, f"Error: {res_att_valido.text}"
        hoja_larga = res_att_valido.json()
        assert hoja_larga["estado"] == "PRE_DESPACHO"
        assert len(hoja_larga["tripulacion"]) == 2
        print(f" -> Hoja de Ruta '{hoja_larga['codigo_hoja']}' creada exitosamente en estado PRE_DESPACHO.")

        # 5. Programación de ruta corta (<= 4h) con 1 solo chofer (DEBE SER PERMITIDO)
        print("\n[4/6] Probando ruta corta (<= 4.0 hrs) con 1 solo conductor Principal...")
        # Usar conductor 3 y 4 para evitar conflicto con los choferes ocupados en hoja_larga
        c3_id = str(conductores[2].id)
        res_corta = client.post(
            "/api/v1/hojas-de-ruta",
            headers={"Authorization": f"Bearer {token_admin}"},
            json={
                "codigo_hoja": "HR-2026-COR-01",
                "vehiculo_id": str(bus_104.id),
                "origen_ciudad": "La Paz",
                "origen_terminal": "Terminal Metropolitana",
                "destino_ciudad": "Oruro",
                "destino_terminal": "Terminal de Oruro",
                "duracion_estimada_hrs": 3.5,
                "fecha_salida": (datetime.utcnow() + timedelta(hours=3)).isoformat(),
                "fecha_llegada_estimada": (datetime.utcnow() + timedelta(hours=6, minutes=30)).isoformat(),
                "tripulantes": [
                    {"conductor_id": c3_id, "tipo_conductor": "PRINCIPAL"}
                ]
            }
        )
        assert res_corta.status_code == 201, f"Error: {res_corta.text}"
        print(" -> Hoja de Ruta de trayecto corto autorizada para un solo conductor.")

        # 6. FLUJO DE PRE-DESPACHO (ALCOTEST EN TERMINAL Y EXCLUSIVO ADMIN)
        print("\n[5/6] Probando Validación de Pre-Despacho (Doble alcotest, reasignación y rol Admin)...")
        hoja_id = hoja_larga["id"]

        # 6.0 Operador intentando pre-despacho -> Bloqueo HTTP 403 (Exclusivo Jefe de Operaciones)
        res_alco_op = client.post(
            "/api/v1/pre-despacho",
            headers={"Authorization": f"Bearer {token_operador}"},
            json={
                "hoja_de_ruta_id": hoja_id,
                "resultado_alcotest_principal": 0.00,
                "observaciones": "Intento de operador"
            }
        )
        assert res_alco_op.status_code == 403
        print(" -> Bloqueo exitoso (HTTP 403): Operador no tiene permisos para realizar pre-despacho.")

        # 6.1 Prueba con Alcotest positivo en relevo (> 0.00) -> NO autoriza
        res_alco_pos = client.post(
            "/api/v1/pre-despacho",
            headers={"Authorization": f"Bearer {token_admin}"},
            json={
                "hoja_de_ruta_id": hoja_id,
                "resultado_alcotest_principal": 0.00,
                "resultado_alcotest_relevo": 0.25,
                "observaciones": "Chofer de relevo dio positivo"
            }
        )
        assert res_alco_pos.status_code == 201
        assert res_alco_pos.json()["aprobado"] is False
        assert res_alco_pos.json()["aprobado_relevo"] is False
        detalle_hoja = client.get(f"/api/v1/hojas-de-ruta/{hoja_id}", headers={"Authorization": f"Bearer {token_admin}"}).json()
        assert detalle_hoja["estado"] == "PRE_DESPACHO"
        print(" -> Alcotest positivo en relevo (0.25 mg/L): Despacho bloqueado en PRE_DESPACHO.")

        # 6.2 Reasignación de conductor de relevo en PRE_DESPACHO (Debe ser un chofer ubicado en La Paz)
        db = SessionLocal()
        cond_lp = db.query(Conductor).filter(
            Conductor.ubicacion_actual == "La Paz",
            ~Conductor.id.in_([conductores[0].id, conductores[1].id])
        ).first()
        nuevo_relevo_id = str(cond_lp.id) if cond_lp else str(conductores[0].id)
        db.close()

        res_reasig = client.post(
            "/api/v1/reasignar-conductor",
            headers={"Authorization": f"Bearer {token_admin}"},
            json={
                "hoja_de_ruta_id": hoja_id,
                "tipo_conductor": "RELEVO",
                "nuevo_conductor_id": nuevo_relevo_id
            }
        )
        assert res_reasig.status_code == 200, f"Error reasignando: {res_reasig.text}"
        print(f" -> Conductor de relevo reasignado exitosamente en estado PRE_DESPACHO.")

        # 6.3 Nuevo pre-despacho con ambos conductores en 0.00 mg/L -> Pasa a AUTORIZADA
        res_alco_doble_ok = client.post(
            "/api/v1/pre-despacho",
            headers={"Authorization": f"Bearer {token_admin}"},
            json={
                "hoja_de_ruta_id": hoja_id,
                "resultado_alcotest_principal": 0.00,
                "resultado_alcotest_relevo": 0.00,
                "observaciones": "Ambos conductores sobrios (0.00 mg/L). Autorizado."
            }
        )
        assert res_alco_doble_ok.status_code == 201
        assert res_alco_doble_ok.json()["aprobado"] is True
        detalle_hoja = client.get(f"/api/v1/hojas-de-ruta/{hoja_id}", headers={"Authorization": f"Bearer {token_admin}"}).json()
        assert detalle_hoja["estado"] == "AUTORIZADA"
        print(" -> Doble alcotest negativo (0.00 mg/L): Hoja de ruta transicionó a AUTORIZADA.")

        # 6.4 Pre-despacho de la ruta corta con Alcotest único = 0.00 mg/L
        hoja_corta_id = res_corta.json()["id"]
        res_alco_cero = client.post(
            "/api/v1/pre-despacho",
            headers={"Authorization": f"Bearer {token_admin}"},
            json={
                "hoja_de_ruta_id": hoja_corta_id,
                "resultado_alcotest_principal": 0.00,
                "observaciones": "Control de alcoholemia negativo. Conductor único óptimo."
            }
        )
        assert res_alco_cero.status_code == 201
        assert res_alco_cero.json()["aprobado"] is True

        detalle_corta = client.get(f"/api/v1/hojas-de-ruta/{hoja_corta_id}", headers={"Authorization": f"Bearer {token_admin}"}).json()
        assert detalle_corta["estado"] == "AUTORIZADA"
        print(" -> Ruta corta: Alcotest único negativo (0.00 mg/L) aprobado a AUTORIZADA.")

        # 7. Inicio y Fin de Tránsito
        print("\n[6/6] Probando confirmación de salida a carretera y finalización...")
        res_transito = client.post(
            f"/api/v1/hojas-de-ruta/{hoja_corta_id}/iniciar-transito",
            headers={"Authorization": f"Bearer {token_operador}"}
        )
        assert res_transito.status_code == 200
        assert res_transito.json()["estado"] == "EN_TRANSITO"
        print(" -> Hoja de Ruta y Bus Interno #TC-004 en estado EN_TRANSITO.")

        res_fin = client.post(
            f"/api/v1/hojas-de-ruta/{hoja_corta_id}/finalizar",
            headers={"Authorization": f"Bearer {token_operador}"}
        )
        assert res_fin.status_code == 200
        assert res_fin.json()["estado"] == "FINALIZADA"
        print(" -> Viaje finalizado correctamente y bus liberado a DISPONIBLE.")

        print("\n=================================================================")
        print("  RESULTADO: TODAS LAS PRUEBAS DE LA FASE 3 PASARON CON ÉXITO    ")
        print("=================================================================")
    finally:
        # Limpieza posterior
        limpiar_datos_prueba()

if __name__ == "__main__":
    test_fase3()
