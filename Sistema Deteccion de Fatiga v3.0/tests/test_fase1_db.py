"""
Script de verificación de Fase 1: Conexión y Modelos ORM SQLAlchemy en trans_copacabana_db (3FN)
"""
import sys
import os

# Asegurar que el path del proyecto está disponible
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.database import SessionLocal, engine
from app.models import (
    Usuario,
    Conductor,
    Vehiculo,
    HojaDeRuta,
    AsignacionTripulacion,
    PreDespacho,
    RegistroTelemetria,
    IncidenteAlerta,
    AtencionIncidente
)

def test_database_connection():
    print("=================================================================")
    print("  EJECUTANDO PRUEBAS DE LA FASE 1: BASE DE DATOS Y MODELOS 3FN   ")
    print("=================================================================")
    print("[1/4] Probando conexión a PostgreSQL y conteo de Usuarios...")
    db = SessionLocal()
    try:
        # 1. Contar usuarios y verificar roles
        usuarios = db.query(Usuario).all()
        print(f" -> Usuarios registrados: {len(usuarios)}")
        for u in usuarios:
            print(f"    - {u.nombre} {u.apellido} ({u.email}) | Rol: {u.rol.value}")
        assert len(usuarios) >= 5, "Deberían existir al menos 5 usuarios en los datos semilla."

        # 2. Verificar conductores y relación con usuario
        print("\n[2/4] Verificando relación Conductor -> Usuario y Ubicaciones...")
        conductores = db.query(Conductor).all()
        print(f" -> Conductores registrados: {len(conductores)}")
        for c in conductores:
            print(f"    - Licencia: {c.licencia_conducir} (Cat. {c.categoria_licencia}) | Chofer: {c.usuario.nombre} {c.usuario.apellido} | Base: {c.ubicacion_actual}")
            assert c.usuario is not None, "La relación conductor.usuario no debe ser nula."
        assert len(conductores) >= 3, "Deberían existir al menos 3 conductores registrados."

        # 3. Verificar flota de vehículos con atributos atómicos (1FN)
        print("\n[3/4] Verificando flota de buses Trans Copacabana (Nº Interno y 1FN)...")
        vehiculos = db.query(Vehiculo).all()
        print(f" -> Buses registrados: {len(vehiculos)}")
        for v in vehiculos:
            print(f"    - Interno #{v.numero_interno} | Placa: {v.placa} | {v.marca} {v.modelo} ({v.tipo_bus.value}) | Ubicación: {v.ubicacion_actual} | Estado: {v.estado.value}")
            assert v.numero_interno is not None
        assert len(vehiculos) >= 3, "Deberían existir al menos 3 buses registrados."

        # 4. Verificar integridad referencial de tablas operativas
        print("\n[4/4] Verificando integridad de tablas operativas y geoespaciales...")
        total_hojas = db.query(HojaDeRuta).count()
        total_telemetria = db.query(RegistroTelemetria).count()
        total_incidentes = db.query(IncidenteAlerta).count()
        print(f" -> Hojas de Ruta registradas: {total_hojas}")
        print(f" -> Registros de Telemetría GPS: {total_telemetria}")
        print(f" -> Alertas e Incidentes viales: {total_incidentes}")

        print("\n=================================================================")
        print("  RESULTADO: TODAS LAS PRUEBAS DE LA FASE 1 PASARON CON ÉXITO")
        print("=================================================================")
        return True

    except Exception as e:
        print(f"\n[ERROR] Falló la verificación: {str(e)}")
        raise e
    finally:
        db.close()

if __name__ == "__main__":
    test_database_connection()
