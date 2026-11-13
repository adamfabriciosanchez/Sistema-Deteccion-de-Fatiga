import psycopg2

def run_migration():
    conn = psycopg2.connect(
        user="postgres",
        password="Pulg42,",
        host="localhost",
        port=5432,
        dbname="trans_copacabana_db"
    )
    cur = conn.cursor()

    # 1. Crear tabla camara_vehiculo
    print("[1/5] Creando tabla camara_vehiculo...")
    cur.execute("""
        CREATE TABLE IF NOT EXISTS camara_vehiculo (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            vehiculo_id UUID NOT NULL UNIQUE REFERENCES vehiculo(id) ON DELETE CASCADE,
            codigo_camara VARCHAR(50) NOT NULL UNIQUE,
            marca_modelo VARCHAR(100) DEFAULT 'Cámara Celular Cabina',
            tipo_dispositivo VARCHAR(50) DEFAULT 'CELULAR_CONDUCTOR',
            resolucion VARCHAR(20) DEFAULT '640x480',
            estado VARCHAR(20) DEFAULT 'ACTIVA',
            fecha_registro TIMESTAMP WITH TIME ZONE DEFAULT NOW()
        );
        CREATE INDEX IF NOT EXISTS idx_camara_vehiculo_id ON camara_vehiculo(vehiculo_id);
    """)

    # 2. Purgar telemetría e incidentes de simulaciones
    print("[2/5] Purgando registros de simulaciones anteriores...")
    cur.execute("DELETE FROM atencion_incidente;")
    cur.execute("DELETE FROM incidente_alerta;")
    cur.execute("DELETE FROM registro_telemetria;")

    # 3. Finalizar hojas de ruta antiguas que quedaron abandonadas
    print("[3/5] Actualizando hojas de ruta vencidas...")
    cur.execute("""
        UPDATE hoja_de_ruta 
        SET estado = 'FINALIZADA',
            fecha_fin_real = COALESCE(fecha_fin_real, NOW())
        WHERE estado = 'EN_TRANSITO';
    """)

    # 4. Restablecer vehículos a DISPONIBLE
    print("[4/5] Restableciendo estado de vehículos a DISPONIBLE...")
    cur.execute("UPDATE vehiculo SET estado = 'DISPONIBLE';")

    # 5. Registrar cámaras 1 a 1 para los vehículos existentes
    print("[5/5] Registrando cámaras para los vehículos...")
    cur.execute("SELECT id, numero_interno FROM vehiculo;")
    vehiculos = cur.fetchall()
    for vid, num_interno in vehiculos:
        cod = f"CAM-BUS-{num_interno}"
        cur.execute("""
            INSERT INTO camara_vehiculo (vehiculo_id, codigo_camara, marca_modelo, tipo_dispositivo, estado)
            VALUES (%s, %s, 'Cámara Inteligente Cabina', 'CELULAR_CONDUCTOR', 'ACTIVA')
            ON CONFLICT (vehiculo_id) DO NOTHING;
        """, (vid, cod))

    conn.commit()
    conn.close()
    print(">>> Migración y limpieza ejecutadas con éxito total.")

if __name__ == "__main__":
    run_migration()

