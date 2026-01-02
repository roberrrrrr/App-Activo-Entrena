"""
Configuración de conexión a PostgreSQL
Lee las variables del archivo .env para mayor seguridad
"""
import psycopg2
import os
from dotenv import load_dotenv # Importamos la librería para leer el .env

# 1. Cargar las variables del archivo .env
# Esto busca el archivo .env y carga su contenido en el sistema
load_dotenv()

# 2. Configuración de la base de datos PostgreSQL
# Ahora leemos desde os.getenv (si no encuentra algo, usa el valor por defecto)
DB_CONFIG = {
    "host": os.getenv("DB_HOST", "localhost"),
    "port": int(os.getenv("DB_PORT", "5432")),
    "database": os.getenv("DB_NAME", "flutter_app_db"),
    "user": os.getenv("DB_USER", "postgres"),
    "password": os.getenv("DB_PASSWORD", ""), 
}

def get_db_connection():
    """
    Crea y retorna una conexión a PostgreSQL
    
    Returns:
        psycopg2.connection: Conexión a la base de datos
    
    Raises:
        psycopg2.Error: Si hay un error al conectar
    """
    try:
        # Usa el diccionario que acabamos de llenar con datos del .env
        conn = psycopg2.connect(**DB_CONFIG)
        return conn
    except psycopg2.Error as e:
        # Imprimimos el error para saber qué pasó (útil para depurar)
        print(f"❌ Error conectando a la DB: {e}")
        raise Exception(f"Error al conectar a PostgreSQL: {str(e)}")