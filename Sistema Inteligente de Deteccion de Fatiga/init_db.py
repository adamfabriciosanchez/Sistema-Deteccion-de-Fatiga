import psycopg2
from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT
import os

DB_USER = "postgres"
DB_PASSWORD = "Pulg42,"
DB_HOST = "localhost"
DB_PORT = "5432"
DB_NAME = "trans_copacabana_db"

def init_db():
    try:
        # Connect to default postgres database to drop/create the new one
        conn = psycopg2.connect(dbname='postgres', user=DB_USER, password=DB_PASSWORD, host=DB_HOST, port=DB_PORT)
        conn.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
        cursor = conn.cursor()
        
        # In case there are active connections, terminate them first to allow dropping
        cursor.execute(f"""
            SELECT pg_terminate_backend(pg_stat_activity.pid)
            FROM pg_stat_activity
            WHERE pg_stat_activity.datname = '{DB_NAME}'
            AND pid <> pg_backend_pid();
        """)
        
        cursor.execute(f"DROP DATABASE IF EXISTS {DB_NAME};")
        cursor.execute(f"CREATE DATABASE {DB_NAME};")
        cursor.close()
        conn.close()
        print(f"Database {DB_NAME} recreated successfully.")

        # Connect to the new database and execute scripts
        conn = psycopg2.connect(dbname=DB_NAME, user=DB_USER, password=DB_PASSWORD, host=DB_HOST, port=DB_PORT)
        cursor = conn.cursor()
        
        with open("database/schema.sql", "r", encoding="utf-8") as f:
            schema_sql = f.read()
        cursor.execute(schema_sql)
        print("Schema executed successfully.")

        with open("database/seed_data.sql", "r", encoding="utf-8") as f:
            seed_sql = f.read()
        cursor.execute(seed_sql)
        print("Seed data executed successfully.")

        conn.commit()
        cursor.close()
        conn.close()
        print("All done.")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    init_db()
