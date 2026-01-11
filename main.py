"""
Backend FastAPI para la aplicación Flutter
Conecta a PostgreSQL y maneja autenticación y registro
"""
from typing import List
from fastapi import FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import psycopg2
from psycopg2.extras import RealDictCursor
from config import get_db_connection
import math
import json
from datetime import date
import time
import httpx


from contextlib import asynccontextmanager
from apscheduler.schedulers.background import BackgroundScheduler
import requests

import os
import httpx # <--- IMPORTANTE
from dotenv import load_dotenv
from fastapi.responses import RedirectResponse

# Cargar variables del .env
load_dotenv()

def scheduled_season_check():
    print("⏰ Ejecutando chequeo automático...")
    try:
        # Se llama a sí mismo para ejecutar la lógica de cierre
        requests.post("http://activo-entrena-9e40e8.up.railway.app/api/admin/process-pending-closures")
    except Exception as e:
        print(f"Error: {e}")

# 2. DEFINIR EL CICLO DE VIDA (LIFESPAN)
# Aquí es donde ocurre la magia del encendido y apagado
@asynccontextmanager
async def lifespan(app: FastAPI):
    # --- LO QUE PASA ANTES DE ARRANCAR ---
    scheduler = BackgroundScheduler()
    scheduler.add_job(scheduled_season_check, 'cron', hour=12, minute=15)
    scheduler.start()
    print("✅ Planificador iniciado")
    
    yield # <--- ESTO ES EL MOMENTO EN QUE LA APP ESTÁ CORRIENDO Y RESPONDIENDO
    
    # --- LO QUE PASA AL APAGAR (CTRL + C) ---
    scheduler.shutdown()
    print("🛑 Planificador detenido")

# 3. CREAR LA APP (Pasándole el lifespan)

app = FastAPI(
    title="Flutter App Backend", 
    version="1.0.1", 
    lifespan=lifespan # <--- AQUÍ SE CONECTA
)
# Configurar CORS para permitir peticiones desde Flutter
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # En producción, especifica el origen exacto
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
# Modelos Pydantic para validación de datos
class AuthRequest(BaseModel):
    """Modelo base para Login y Register"""
    userName: str
    password: str



class RegisterResponse(BaseModel):
    success: bool
    message: str
    user_id: int | None = None
    username: str | None = None

class UserResponse(BaseModel):
    id: int
    username: str
    is_strava_connected: bool  # <--- Este es el campo nuevo para el frontend

    class Config:
        from_attributes = True

class LoginResponse(BaseModel):
    success: bool
    message: str
    user: UserResponse | None = None

class LatLng(BaseModel):
    lat: float
    lng: float

class RunCreate(BaseModel):
    user_id: str  # O int, depende de cómo definiste tu tabla users
    
    points: List[LatLng]

class UserStats(BaseModel):
    total_distance_km: float
    total_elevation_m: float # altimetria
    season_name: str
    is_strava_connected: bool = False  # Indica si el usuario tiene Strava conectado

class LeaderboardEntry(BaseModel):
    username: str
    user_id: int
    value: float # Puede ser km o m2
    rank: int

@app.get("/")
async def root():
    """Endpoint de prueba para verificar que el servidor está corriendo"""
    return {"message": "Backend Flutter App está funcionando", "status": "ok"}


# --- RUTAS DE AUTENTICACIÓN ---

@app.post("/api/auth/login", response_model=LoginResponse)
async def login(auth_data: AuthRequest):
    """
    Endpoint de login que valida credenciales contra PostgreSQL
    """
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        
        # Consultar usuario por username
        query = "SELECT id, username, password, strava_athlete_id FROM users WHERE username = %s"
        cursor.execute(query, (auth_data.userName,))
        user = cursor.fetchone()
        
        if not user:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Credenciales inválidas"
            )
        
        # Verificar contraseña (comparación simple por ahora)
        if user['password'] != auth_data.password:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Credenciales inválidas"
            )
        
        # 2. CAMBIO AQUÍ: Calculamos si está conectado
        # Si strava_athlete_id tiene un número, es True. Si es None, es False.
        is_connected = user['strava_athlete_id'] is not None

        # Login exitoso
        user_data = {
            "id": user['id'],
            "username": user['username'],
            "is_strava_connected": is_connected
        }
        
        return LoginResponse(
            success=True,
            message="Login exitoso",
            user=user_data
        )
        
    except HTTPException:
        # Re-lanzar excepciones HTTP
        raise
    except psycopg2.Error as e:
        # Error de base de datos
        print(f"Database Error: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error de base de datos: {str(e)}"
        )
    except Exception as e:
        # Error inesperado
        print(f"Unexpected Error: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error interno del servidor: {str(e)}"
        )
    finally:
        # Cerrar conexión
        if conn:
            cursor.close()
            conn.close()


@app.post("/api/auth/register", response_model=RegisterResponse)
async def register(auth_data: AuthRequest):
    """
    Endpoint de registro que inserta un nuevo usuario en la base de datos.
    """
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # 1. Verificar si el usuario ya existe
        check_query = "SELECT 1 FROM users WHERE username = %s"
        cursor.execute(check_query, (auth_data.userName,))
        if cursor.fetchone() is not None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="El nombre de usuario ya está en uso."
            )
            
        # 2. Insertar nuevo usuario
        # IMPORTANTE: La cláusula RETURNING 'id' nos devuelve el ID generado.
        insert_query = """
            INSERT INTO users (username, password) 
            VALUES (%s, %s) RETURNING id
        """
        cursor.execute(insert_query, (auth_data.userName, auth_data.password))
        
        # Obtener el ID del nuevo usuario
        new_user_id = cursor.fetchone()[0]
        
        # 3. Confirmar la transacción
        conn.commit()
        
        return RegisterResponse(
            success=True,
            message="Registro exitoso. Usuario creado.",
            user_id=new_user_id,
            username=auth_data.userName
        )
        
    except HTTPException:
        # Re-lanzar excepciones HTTP
        raise
    except psycopg2.Error as e:
        if conn:
            conn.rollback() # Deshacer si hay error de DB
        print(f"Database Error during registration: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error de base de datos durante el registro: {str(e)}"
        )
    except Exception as e:
        if conn:
            conn.rollback()
        print(f"Unexpected Error during registration: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error interno del servidor: {str(e)}"
        )
    finally:
        if conn:
            cursor.close()
            conn.close()




# --- FUNCIÓN AUXILIAR: Fórmula de Haversine (Distancia entre 2 puntos) ---
def calculate_distance(lat1, lon1, lat2, lon2):
    R = 6371000 # Radio de la tierra en metros
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    delta_phi = math.radians(lat2 - lat1)
    delta_lambda = math.radians(lon2 - lon1)

    a = math.sin(delta_phi / 2.0) ** 2 + \
        math.cos(phi1) * math.cos(phi2) * \
        math.sin(delta_lambda / 2.0) ** 2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    print("distancia calculada:", R * c)
    return R * c
# --- ENDPOINT PARA GUARDAR RECORRIDO ---
@app.post("/api/runs")
def create_run(run: RunCreate):
    if len(run.points) < 3: 
        raise HTTPException(status_code=400, detail="Recorrido muy corto")

    # 1. Verificar si es Cerrado (Start vs End < 50 metros)
    start_point = run.points[0]
    end_point = run.points[-1]
    
    distance_gap = calculate_distance(
        start_point.lat, start_point.lng, 
        end_point.lat, end_point.lng
    )
    
    is_closed_loop = distance_gap < 50.0 

    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        # --- NUEVO: DETECTAR TEMPORADA AUTOMÁTICAMENTE ---
        # Buscamos la temporada activa que coincida con la fecha de hoy
        cursor.execute("""
            SELECT id FROM seasons 
            WHERE CURRENT_DATE BETWEEN start_date AND end_date 
            LIMIT 1
        """)
        season_row = cursor.fetchone()
        
        if not season_row:
            # Si no hay temporada (ej. estamos en un hueco temporal o todas están inactivas)
            raise HTTPException(
                status_code=400, 
                detail="No hay una temporada activa para la fecha de hoy. Contacta al administrador."
            )
            
        current_season_id = season_row[0] # <--- ESTE ES EL ID QUE USAREMOS
        # -------------------------------------------------

        # Preparar WKT
        points_str_list = [f"{p.lng} {p.lat}" for p in run.points]
        wkt_linestring = f"LINESTRING({', '.join(points_str_list)})"

        # --- A. GUARDAR EN USER_RUNS ---
        query_run = """
            INSERT INTO user_runs (user_id, season_id, geom, distance_meters)
            VALUES (
                %s, %s, 
                ST_GeomFromText(%s, 4326), 
                ST_Length(ST_GeomFromText(%s, 4326)::geography)
            )
            RETURNING distance_meters;
        """
        # CAMBIO: Usamos 'current_season_id' en lugar de 'run.season_id'
        cursor.execute(query_run, (run.user_id, current_season_id, wkt_linestring, wkt_linestring))
        distance_meters = cursor.fetchone()[0]

        # --- B. SI ES CERRADO, ACTUALIZAR TERRITORIOS ---
        territory_msg = "Recorrido abierto (no conquista territorio)"
        
        if is_closed_loop:
            query_territory = """
            INSERT INTO territories (user_id, season_id, geom, area_sq_meters)
            VALUES (
                %s, %s,
                ST_MakePolygon(ST_AddPoint(ST_GeomFromText(%s, 4326), ST_StartPoint(ST_GeomFromText(%s, 4326)))),
                0 
            )
            ON CONFLICT (user_id, season_id) 
            DO UPDATE SET 
                geom = ST_Union(territories.geom, EXCLUDED.geom),
                created_at = NOW();
            """
            
            # CAMBIO: Usamos 'current_season_id'
            cursor.execute(query_territory, (run.user_id, current_season_id, wkt_linestring, wkt_linestring))
            
            # Actualizar el área total
            cursor.execute("""
                UPDATE territories 
                SET area_sq_meters = ST_Area(geom::geography) 
                WHERE user_id = %s AND season_id = %s
            """, (run.user_id, current_season_id)) # CAMBIO: Usamos 'current_season_id'
            
            territory_msg = "¡Territorio conquistado/expandido!"

        conn.commit()

        return {
            "message": "Guardado exitoso", 
            "distance_meters": distance_meters,
            "territory_status": territory_msg,
            "is_closed": is_closed_loop,
            "season_id": current_season_id # Opcional: devolvemos la temporada detectada
        }

    except HTTPException as http_ex:
        conn.rollback()
        raise http_ex
    except Exception as e:
        conn.rollback()
        print(f"Error: {e}") 
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        cursor.close()
        conn.close()

#---------------------------------------------------
#      ENDPOINT PARA AOBTENER EL TOKEN DE STRAVA
#---------------------------------------------------
async def get_valid_token_raw(user_id, cursor):
    #obtener los tokens actuales del usuario
    cursor.execute(""" SELECT strava_access_token, strava_refresh_token, strava_token_expires_at
                   FROM users WHERE id = %s""",  (user_id,))
    row = cursor.fetchone()
    if not row:
        raise Exception(status_code=404, detail="Usuario no encontrado")

    access_token, refresh_token, expires_at = row
    #verificar expiracion, se dan 60 segundos de margen
    current_time = int(time.time())
    if expires_at and current_time < (expires_at -60):
        return access_token #el token sirve
        
    #si el token expiró
    async with httpx.AsyncClient() as client:
        response = await client.post("https://www.strava.com/oauth/token",
                                      data={"client_id": STRAVA_CLIENT_ID, 
                                            "client_secret": STRAVA_CLIENT_SECRET, 
                                            "grant_type": "refresh_token", 
                                            "refresh_token": refresh_token, },)

    if response.status_code !=200:
        raise Exception(status_code=400, detail="Error al refrescar token de Strava")
    
    data = response.json()
    new_access = data["access_token"]
    new_refresh = data["refresh_token"]
    new_expires = data["expires_at"]

    # Actualizar BD
    cursor.execute(""" UPDATE users SET strava_access_token =%s, strava_refresh_token = %s, strava_token_expires_at = %s 
                   where id = %s""",
                     (new_access, new_refresh, new_expires, user_id))
    
    return new_access

# --- 1. ASEGÚRATE DE QUE ESTOS IMPORTS ESTÉN AL INICIO DEL ARCHIVO ---
import httpx
import traceback
from math import radians, cos, sin, asin, sqrt
from fastapi import HTTPException

# --- 2. FUNCIÓN AUXILIAR (Por si la borraste sin querer) ---
def calculate_distance(lon1, lat1, lon2, lat2):
    """
    Calcula la distancia en metros entre dos puntos (Haversine formula).
    """
    try:
        lon1, lat1, lon2, lat2 = map(radians, [lon1, lat1, lon2, lat2])
        dlon = lon2 - lon1
        dlat = lat2 - lat1
        a = sin(dlat/2)**2 + cos(lat1) * cos(lat2) * sin(dlon/2)**2
        c = 2 * asin(sqrt(a))
        r = 6371000 # Radio de la Tierra en metros
        return c * r
    except Exception:
        return 0.0

# --- 3. EL ENDPOINT BLINDADO (Con la ruta /api corregida) ---
@app.post("/api/sync/last-activity-raw")  # <--- OJO: AHORA TIENE /api
async def sync_last_activity_raw(user_id: int):
    print(f"\n🚀 [INICIO] Sync solicitado para User ID: {user_id}")
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        # --- A. OBTENER TOKEN ---
        print("👉 [Paso 1] Buscando token en DB...")
        token = await get_valid_token_raw(user_id, cursor)
        if not token:
             print("❌ [Error] No se encontró token para este usuario.")
             raise HTTPException(status_code=400, detail="Usuario no conectado a Strava")
        print(f"✅ [Paso 1] Token obtenido (inicia con {token[:5]}...)")
        
        # --- B. LLAMAR A STRAVA ---
        print("👉 [Paso 2] Consultando API de Strava (última actividad)...")
        headers = {"Authorization": f"Bearer {token}"}
        
        async with httpx.AsyncClient() as client:
            act_resp = await client.get("https://www.strava.com/api/v3/athlete/activities?per_page=1", headers=headers)
            
            if act_resp.status_code != 200:
                print(f"❌ [Error Strava] Código: {act_resp.status_code} - Body: {act_resp.text}")
                raise HTTPException(status_code=400, detail=f"Error API Strava: {act_resp.status_code}")
            
            activities = act_resp.json()
            if not activities:
                print("⚠️ [Aviso] El usuario no tiene actividades en Strava.")
                return {"message": "No hay actividades recientes"}
            
            last_run = activities[0]
            strava_id = str(last_run['id'])
            name_run = last_run.get('name', 'Carrera sin nombre')
            print(f"✅ [Paso 3] Actividad encontrada: ID {strava_id} - '{name_run}'")
            
            # --- NUEVO: OBTENER ELEVACIÓN ---
            # Si es plano devuelve 0.0
            elevation_gain = float(last_run.get('total_elevation_gain', 0.0))

            # VERIFICAR DUPLICADOS
            cursor.execute("SELECT 1 FROM user_runs WHERE strava_id = %s AND user_id = %s", (strava_id, user_id))
            if cursor.fetchone():
                print("⏸️ [Fin] La actividad ya existía en DB.")
                return {"message": "Actividad ya sincronizada", "synced": True}

            # OBTENER COORDENADAS
            print("👉 [Paso 4] Descargando coordenadas (streams)...")
            streams_resp = await client.get(
                f"https://www.strava.com/api/v3/activities/{strava_id}/streams?keys=latlng&key_by_type=true",
                headers=headers
            )
            streams = streams_resp.json()
            
            # --- VALIDACIÓN CRÍTICA: GIMNASIO O ERROR ---
            if 'latlng' not in streams or not streams['latlng']['data']:
                print("⚠️ [Fin] Actividad sin mapa (posiblemente Indoor/Gimnasio).")
                return {"error": "Esta actividad no tiene mapa GPS, no cuenta para territorio."}
            
            raw_coords = streams['latlng']['data']
            print(f"✅ [Paso 4] Coordenadas recibidas: {len(raw_coords)} puntos.")
            
            if len(raw_coords) < 2:
                return {"error": "Recorrido inválido (menos de 2 puntos)"}

        # --- C. PREPARAR GEOMETRÍA ---
        print("👉 [Paso 5] Convirtiendo a formato PostGIS...")
        # PostGIS usa: LONGITUD LATITUD (Strava manda: Lat, Long) -> Invertimos p[1] p[0]
        points_str_list = [f"{p[1]} {p[0]}" for p in raw_coords]
        wkt_linestring = f"LINESTRING({', '.join(points_str_list)})"
        
        # ------------------ESTO NO VA -----------------#
        """# --- D. DETECTAR SI ES CERRADO ---
        start_p = raw_coords[0]
        end_p = raw_coords[-1]
        distance_gap = calculate_distance(start_p[0], start_p[1], end_p[0], end_p[1])
        is_closed_loop = distance_gap < 50.0
        """

        # --- E. DETECTAR TEMPORADA ---
        print("👉 [Paso 6] Buscando temporada actual...")
        cursor.execute("""
            SELECT id FROM seasons 
            WHERE CURRENT_DATE BETWEEN start_date AND end_date 
            LIMIT 1
        """)
        season_row = cursor.fetchone()
        if not season_row:
             # Si no hay temporada, usamos null o lanzamos error. Aquí lanzo error para que lo sepas.
             print("❌ [Error] No hay temporada configurada en la DB.")
             raise HTTPException(status_code=400, detail="No hay temporada activa en el juego.")
        current_season_id = season_row[0]

        # --- F. GUARDAR RECORRIDO ---
        print("👉 [Paso 7] Insertando carrera en user_runs...")
        query_run = """
            INSERT INTO user_runs (user_id, season_id, strava_id, geom, distance_meters, elevation_gain)
            VALUES (
                %s, %s, %s,
                ST_GeomFromText(%s, 4326), 
                ST_Length(ST_GeomFromText(%s, 4326)::geography), 
                %s
                )
                RETURNING distance_meters;
            
        """
        cursor.execute(query_run, (user_id, current_season_id, strava_id, wkt_linestring, wkt_linestring, elevation_gain))
        distance_meters = cursor.fetchone()[0]
        conn.commit()

        print(f"✅ [ÉXITO] Guardado: {distance_meters:.0f}m distancia, {elevation_gain:.0f}m altura.")

        return {
            "status": "success",
            "message": f"¡Guardado! +{elevation_gain}m escalados.",
            "added_elevation": elevation_gain,
            "added_distance": distance_meters
        }

        # ------  ESTO NO VA ------- #
        # # --- G. ACTUALIZAR TERRITORIOS ---
        # territory_msg = "Carrera guardada (Ruta abierta)"
        
        # if is_closed_loop:
        #     print("👉 [Paso 8] ¡Loop cerrado detectado! Calculando territorio...")
        #     if len(raw_coords) >= 3:
        #         # ---------------------------------------------------------
        #         # COMIENZO DEL BLOQUE MODIFICADO "CHIVATO" 🕵️‍♂️
        #         # ---------------------------------------------------------
                
        #         query_territory = """
        #         WITH linea_base AS (
        #             SELECT ST_GeomFromText(%s, 4326) as geom
        #         ),
        #         linea_cerrada AS (
        #             /* 1. Cerramos la línea */
        #             SELECT ST_AddPoint(geom, ST_StartPoint(geom)) as geom 
        #             FROM linea_base
        #         ),
        #         calculo_area AS (
        #             /* 2. Intentamos calcular el área interna (PLAN A) */
        #             SELECT ST_MakeValid(ST_BuildArea(geom)) as geom_interna
        #             FROM linea_cerrada
        #         )
        #         INSERT INTO territories (user_id, season_id, geom, area_sq_meters)
        #         SELECT 
        #             %s, 
        #             %s,
        #             /* LOGICA MAESTRA: COALESCE elige el primer valor que NO sea nulo */
        #             ST_Multi(
        #                 COALESCE(
        #                     /* Intento 1: Si hay área interna válida y no vacía, úsala */
        #                     CASE 
        #                         WHEN NOT ST_IsEmpty(geom_interna) AND ST_GeometryType(geom_interna) = 'ST_Polygon' 
        #                         THEN geom_interna 
        #                         ELSE NULL 
        #                     END,
                            
        #                     /* Intento 2 (Plan B): Si falló lo anterior, crea un buffer (grosor) de 2 metros alrededor de la línea */
        #                     ST_Buffer((SELECT geom FROM linea_cerrada)::geography, 2)::geometry
        #                 )
        #             ),
        #             0 -- El área se recalcula bien abajo
        #         FROM calculo_area
        #         ON CONFLICT (user_id, season_id) 
        #         DO UPDATE SET 
        #             geom = ST_Multi(ST_Union(territories.geom, EXCLUDED.geom)),
        #             created_at = NOW()
        #         RETURNING area_sq_meters; 
        #         """

        #         # Ejecutamos (mismo orden de parámetros)
        #         cursor.execute(query_territory, (wkt_linestring, user_id, current_season_id))
                
        #         # --- VERIFICACIÓN FINAL ---
        #         resultado_db = cursor.fetchone()
                
        #         if resultado_db:
        #             # Recalcular área total exacta
        #             cursor.execute("""
        #                 UPDATE territories 
        #                 SET area_sq_meters = ST_Area(geom::geography) 
        #                 WHERE user_id = %s AND season_id = %s
        #                 RETURNING area_sq_meters
        #             """, (user_id, current_season_id))
                    
        #             area_total = cursor.fetchone()[0]
        #             territory_msg = f"¡Territorio conquistado! Área total: {area_total:.2f} m²"
        #             print(f"✅ [Paso 8] ÉXITO: Territorio guardado. Área total: {area_total:.2f} m²")
        #         else:
        #             # Si llega aquí, es imposible matemáticamente (salvo error grave de PostGIS)
        #             print("💀 [Paso 8] IMPOSIBLE: Ni el área interna ni el buffer funcionaron.")

        #         conn.commit() # Asegúrate que este commit esté aquí

        #     else:
        #         print("⚠️ [Aviso] Loop cerrado pero con geometría inválida (menos de 3 puntos).")
        # return {
        #     "status": "success",
        #     "message": territory_msg,
        #     "distance_gap": distance_gap,
        #     "is_closed": is_closed_loop
        # }

    except HTTPException as he:
        # Re-lanzar excepciones HTTP controladas
        raise he
    except Exception as e:
        conn.rollback()
        print("\n💀💀💀 CRASH DEL SERVIDOR 💀💀💀")
        print(f"Error: {str(e)}")
        traceback.print_exc()  # <--- ESTO NOS DARÁ EL ERROR REAL
        print("💀💀💀💀💀💀💀💀💀💀💀💀💀💀\n")
        raise HTTPException(status_code=500, detail=f"Error interno del servidor: {str(e)}")
    finally:
        cursor.close()
        conn.close()


@app.get("/api/territories")
def get_territories(season_id: int = None):
    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        
        # Si no mandan ID, buscamos el actual
        target_season = season_id
        if target_season is None:
            cursor.execute("SELECT id FROM seasons WHERE CURRENT_DATE BETWEEN start_date AND end_date LIMIT 1")
            row = cursor.fetchone()
            if row:
                target_season = row[0]
            else:
                return {"results": []} # No hay temporada, devolvemos vacío
        # Consultamos la geometría como GeoJSON y el ID del usuario
        # ST_AsGeoJSON(geom): Devuelve un string JSON con las coordenadas
        query = """
            SELECT 
                t.user_id, 
                u.username,
                ST_AsGeoJSON(t.geom) as geojson
            FROM territories t
            JOIN users u ON t.user_id = u.id
            WHERE t.season_id = %s
        """
        cursor.execute(query, (target_season,))
        rows = cursor.fetchall()
        print("la temporada es:", target_season)
        results = []
        for row in rows:
            results.append({
                "user_id": row[0],
                "username": row[1],
                "geometry": json.loads(row[2]) # Convertimos el string GeoJSON a Objeto Python
            })

        return { "results": results }

    except Exception as e:
        print(e)
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        cursor.close()
        conn.close()

@app.get("/api/users/{user_id}/runs/history")
def get_user_runs_history(user_id: str, season_id: int = None):
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        # 1. Resolver temporada actual si no viene
        if not season_id:
            cursor.execute("""
                SELECT id FROM seasons 
                WHERE CURRENT_DATE BETWEEN start_date AND end_date 
                LIMIT 1
            """)
            row = cursor.fetchone()
            if row: season_id = row[0]

        if not season_id: return {"results": []}

        # 2. Traer las geometrías de las corridas (Líneas)
        # Usamos ST_AsGeoJSON para obtener las coordenadas de la línea
        cursor.execute("""
            SELECT ST_AsGeoJSON(geom) 
            FROM user_runs 
            WHERE user_id = %s AND season_id = %s
            ORDER BY created_at DESC
            LIMIT 50 -- Limitamos a las últimas 50 para no explotar el mapa
        """, (user_id, season_id))
        
        rows = cursor.fetchall()
        results = [json.loads(row[0]) for row in rows] # Lista de GeoJSONs

        return {"results": results}
    finally:
        cursor.close()
        conn.close()

# --- ENDPOINT 1: ESTADÍSTICAS PERSONALES ---
@app.get("/api/users/{user_id}/stats", response_model=UserStats)
def get_user_stats(user_id: str):
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        # 0. OBTENER is_strava_connected DEL USUARIO (y verificar que existe)
        cursor.execute("""
            SELECT strava_athlete_id FROM users WHERE id = %s
        """, (user_id,))
        user_row = cursor.fetchone()
        
        if not user_row:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Usuario con ID {user_id} no encontrado"
            )
        
        is_strava_connected = user_row[0] is not None

        # 1. BUSCAR TEMPORADA ACTUAL
        cursor.execute("""
            SELECT id, name FROM seasons 
            WHERE CURRENT_DATE BETWEEN start_date AND end_date 
            LIMIT 1
        """)
        season_row = cursor.fetchone()

        # Valores por defecto si no hay temporada
        current_season_id = None
        season_name = "Sin Temporada Activa"

        if season_row:
            current_season_id = season_row[0]
            season_name = season_row[1]

        # 2. CALCULAR DISTANCIA Y ALTIMETRÍA (En una sola consulta) 🚀
        total_dist_m = 0.0
        total_elev_m = 0.0

        if current_season_id is not None:
            # Sumamos distancia y elevación directamente de user_runs
            cursor.execute("""
                SELECT 
                    COALESCE(SUM(distance_meters), 0), 
                    COALESCE(SUM(elevation_gain), 0)
                FROM user_runs 
                WHERE user_id = %s AND season_id = %s
            """, (user_id, current_season_id))
            
            result = cursor.fetchone()
            if result:
                total_dist_m = float(result[0])
                total_elev_m = float(result[1])

        # 3. RETORNAR RESULTADO
        return UserStats(
            total_distance_km=total_dist_m / 1000.0,    # Metros a KM
            total_elevation_m=total_elev_m,             # Metros (Directo)
            season_name=season_name,
            is_strava_connected=is_strava_connected
        )

        # ----- ESTO NO VA ---- #
        # # 3. Calcular Área Total (Tabla territories)
        # # Si no hay temporada activa, devolvemos 0
        # if current_season_id is not None:
        #     cursor.execute("""
        #         SELECT COALESCE(SUM(area_sq_meters), 0) 
        #         FROM territories 
        #         WHERE user_id = %s AND season_id = %s
        #     """, (user_id, current_season_id))
        #     total_area_m2 = cursor.fetchone()[0]
        # else:
        #     total_area_m2 = 0

        # return UserStats(
        #     total_distance_km=total_dist_m / 1000.0, # Convertir a KM
        #     total_area_hectares=total_area_m2 / 10000.0, # Convertir a Hectáreas (1 ha = 10,000 m2)
        #     season_name=season_name,
        #     is_strava_connected=is_strava_connected
        # )
    except HTTPException:
        # Re-lanzar excepciones HTTP
        raise
    except psycopg2.Error as e:
        # Error de base de datos
        print(f"Database Error en get_user_stats: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error de base de datos: {str(e)}"
        )
    except Exception as e:
        # Error inesperado
        print(f"Unexpected Error en get_user_stats: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error interno del servidor: {str(e)}"
        )
    finally:
        cursor.close()
        conn.close()

# --- ENDPOINT 2: RANKINGS (LEADERBOARD) ---
@app.get("/api/leaderboard")
def get_leaderboard(type: str, season_id: int = 1):
    # type puede ser 'distance' o 'hight'
    conn = get_db_connection()
    cursor = conn.cursor()
    try:

        # 1. BUSCAR TEMPORADA ACTUAL
        cursor.execute("""
            SELECT id, name FROM seasons 
            WHERE CURRENT_DATE BETWEEN start_date AND end_date 
            LIMIT 1
        """)
        season_row = cursor.fetchone()

        # Valores por defecto si no hay temporada
        current_season_id = None
        season_name = "Sin Temporada Activa"

        if season_row:
            current_season_id = season_row[0]
            season_name = season_row[1]

        # Si no hay temporada, retornamos lista vacía directo
        if current_season_id is None:
            return { "results": [] }

        # 2. CONFIGURAR COLUMNA Y CONVERSIÓN SEGÚN EL TIPO
        # Definimos qué columna sumar y por cuánto dividir
        if type == 'distance':
            db_column = 'distance_meters'
            divisor = 1000.0  # Metros -> Kilómetros
        elif type == 'hight': # "hight" es el valor que manda tu app
            db_column = 'elevation_gain'
            divisor = 1.0     # Metros -> Metros (No se convierte)
        else:
            # Si mandan un tipo desconocido, devolvemos vacío
            return { "results": [] }

        # 3. CONSULTA DINÁMICA (Optimized)
        # Usamos f-string para la columna porque db_column lo definimos nosotros (es seguro)
        query = f"""
            SELECT u.id, u.username, SUM(r.{db_column}) as total
            FROM user_runs r
            JOIN users u ON r.user_id = u.id
            WHERE r.season_id = %s
            GROUP BY u.id, u.username
            ORDER BY total DESC
            LIMIT 30
        """
        
        cursor.execute(query, (current_season_id,))
        rows = cursor.fetchall()
        
        results = []
        for index, row in enumerate(rows):
            # row ahora tiene 3 elementos: 
            # row[0] = id
            # row[1] = username
            # row[2] = total
            raw_score = float(row[2]) if row[2] is not None else 0.0
        # Aplicamos la división (KM o Metros planos)
            val = raw_score / divisor
            
            results.append({
                "rank": index + 1,
                "user_id": row[0],
                "username": row[1],
                "value": round(val, 2) # Redondeamos a 2 decimales para que se vea bonito
            })
            
        return { "results": results } # Devolvemos formato compatible con tu ApiClient
    finally:
        cursor.close()
        conn.close()

@app.post("/api/admin/process-pending-closures")
def process_pending_season_closures():
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        # 1. BUSCAR TEMPORADAS PENDIENTES DE CIERRE
        # Lógica: Fecha fin ya pasó Y el ID no está en la tabla de podios
        cursor.execute("""
            SELECT id, name FROM seasons 
            WHERE end_date < CURRENT_DATE 
            AND id NOT IN (SELECT DISTINCT season_id FROM season_podiums)
        """)
        pending_seasons = cursor.fetchall()
        
        if not pending_seasons:
            return {"message": "No hay temporadas pendientes de cierre.", "processed": []}

        processed_names = []

        # 2. ITERAR Y CERRAR CADA UNA
        for season in pending_seasons:
            s_id = season[0]
            s_name = season[1]
            
            # A. Calcular Podio Distancia
            cursor.execute("""
                INSERT INTO season_podiums (season_id, user_id, category, rank, final_score)
                SELECT %s, user_id, 'distance', 
                       RANK() OVER (ORDER BY SUM(distance_meters) DESC),
                       SUM(distance_meters) / 1000.0
                FROM user_runs WHERE season_id = %s
                GROUP BY user_id ORDER BY 5 DESC LIMIT 3
            """, (s_id, s_id))

            # B. Calcular Podio Altitud
            # Sumamos elevation_gain (se queda en metros, no se divide)
            # Usamos la categoría 'hight' para mantener consistencia
            cursor.execute("""
                INSERT INTO season_podiums (season_id, user_id, category, rank, final_score)
                SELECT %s, user_id, 'hight', 
                       RANK() OVER (ORDER BY SUM(elevation_gain) DESC),
                       SUM(elevation_gain)
                FROM user_runs WHERE season_id = %s
                GROUP BY user_id 
                ORDER BY 5 DESC -- Ordena por la columna 5 (final_score)
                LIMIT 3
            """, (s_id, s_id))
            
            # C. Marcar temporada como inactiva (opcional, por seguridad)
            cursor.execute("UPDATE seasons SET is_active = false WHERE id = %s", (s_id,))
            
            processed_names.append(s_name)

        conn.commit()
        return {"message": "Cierre masivo exitoso", "closed_seasons": processed_names}

    except Exception as e:
        conn.rollback()
        print(f"Error cerrando temporadas: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        cursor.close()
        conn.close()

@app.get("/api/hall-of-fame/history")
def get_full_history():
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        # Traemos TODO: Temporada, Usuario, Puesto, Categoría
        query = """
            SELECT 
                s.name as season_name,
                s.end_date,
                p.category,
                p.rank,
                u.username,
                p.final_score
            FROM season_podiums p
            JOIN seasons s ON p.season_id = s.id
            JOIN users u ON p.user_id = u.id
            ORDER BY s.end_date DESC, p.category, p.rank
        """
        cursor.execute(query)
        rows = cursor.fetchall()
        
        # PROCESAMIENTO EN PYTHON (Agrupar filas planas en objetos anidados)
        history = {} # Diccionario temporal para agrupar

        for row in rows:
            s_name = row[0]
            
            if s_name not in history:
                history[s_name] = {
                    "season_name": s_name,
                    "end_date": str(row[1]),
                    "champions": []
                }
            
            history[s_name]["champions"].append({
                "category": row[2],
                "rank": row[3],
                "username": row[4],
                "score": row[5]
            })

        # Convertir diccionario a lista limpia
        return {"results": list(history.values())}

    finally:
        cursor.close()
        conn.close()

@app.get("/api/health")
async def health_check():
    """Endpoint para verificar el estado del servidor y la conexión a la BD"""
    try:
        conn = get_db_connection()
        conn.close()
        return {"status": "healthy", "database": "connected"}
    except Exception as e:
        return {"status": "unhealthy", "database": "disconnected", "error": str(e)}

# --- CONFIGURACIÓN DE STRAVA ---
STRAVA_CLIENT_ID = os.getenv("STRAVA_CLIENT_ID")
STRAVA_CLIENT_SECRET = os.getenv("STRAVA_CLIENT_SECRET")
# La URL a la que Strava debe responder (debe coincidir con lo que pusiste en la web de Strava)
REDIRECT_URI = "http://activo-entrena-9e40e8.up.railway.app/api/strava/callback" 
FRONTEND_URL = os.getenv("FRONTEND_URL", "http://localhost:53421") # Puerto de Flutter

@app.get("/api/strava/login")
def strava_login(user_id: int):
    """
    1. Recibe el ID del usuario de la App.
    2. Redirige a Strava.com para pedir permiso.
    3. Pasa el 'user_id' dentro del parámetro 'state' para recordarlo al volver.
    """
    # Scope: activity:read_all es NECESARIO para obtener coordenadas GPS
    scope = "activity:read_all"
    
    # El 'state' es nuestro truco para saber qué usuario está conectando
    state = str(user_id)
    
    url = (
        f"https://www.strava.com/oauth/authorize"
        f"?client_id={STRAVA_CLIENT_ID}"
        f"&response_type=code"
        f"&redirect_uri={REDIRECT_URI}"
        f"&approval_prompt=auto"
        f"&scope={scope}"
        f"&state={state}" # <--- Aquí viaja el ID del usuario
    )
    
    print(f"🔗 Redirigiendo a Strava para el usuario ID: {user_id}")
    return RedirectResponse(url)

@app.get("/api/strava/callback")
async def strava_callback(code: str, state: str, scope: str = None):
    """
    1. Strava nos devuelve a este endpoint con un 'code' temporal.
    2. Intercambiamos ese 'code' por los Tokens reales.
    3. Guardamos los Tokens en la base de datos del usuario (usando el 'state' como ID).
    """
    print(f"🔄 Callback recibido de Strava. Code: {code[:5]}... User ID: {state}")

    # 1. Intercambiar CODE por TOKENS
    async with httpx.AsyncClient() as client:
        response = await client.post(
            "https://www.strava.com/oauth/token",
            data={
                "client_id": STRAVA_CLIENT_ID,
                "client_secret": STRAVA_CLIENT_SECRET,
                "code": code,
                "grant_type": "authorization_code",
            },
        )
    
    if response.status_code != 200:
        error_detail = response.json()
        print(f"❌ Error conectando con Strava: {error_detail}")
        raise HTTPException(status_code=400, detail="Error al obtener tokens de Strava")
    
    data = response.json()
    
    # Extraemos los datos valiosos
    strava_athlete_id = data['athlete']['id']
    access_token = data['access_token']
    refresh_token = data['refresh_token']
    expires_at = data['expires_at']
    
    user_id = int(state) # Recuperamos el ID que enviamos al principio

    # 2. Guardar en Base de Datos (SQL Puro)
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Query de actualización
        update_query = """
            UPDATE users 
            SET strava_athlete_id = %s,
                strava_access_token = %s,
                strava_refresh_token = %s,
                strava_token_expires_at = %s
            WHERE id = %s
        """
        
        cursor.execute(update_query, (
            strava_athlete_id,
            access_token,
            refresh_token,
            expires_at,
            user_id
        ))
        
        conn.commit()
        print(f"✅ Usuario {user_id} vinculado exitosamente con Strava ID {strava_athlete_id}")
        
        # 3. Redirigir al Frontend (Flutter)
        # Agregamos un parámetro '?status=success' para que Flutter pueda mostrar un mensaje
        return RedirectResponse(f"{FRONTEND_URL}/#/dashboard?strava_status=success")

    except psycopg2.Error as e:
        if conn: conn.rollback()
        print(f"❌ Error DB: {e}")
        raise HTTPException(status_code=500, detail="Error guardando datos en DB")
    finally:
        if conn:
            cursor.close()
            conn.close()

if __name__ == "__main__":
    import uvicorn
    # Ejecutar servidor en localhost:8000
    # Para acceder desde emulador Android, usa: uvicorn main:app --host 0.0.0.0 --port 8000
    # 2. Obtenemos el puerto que nos da Railway (variable 'PORT').
    # Si esa variable no existe (porque estás en tu PC), usa el 8000 por defecto.
    port = int(os.environ.get("PORT", 8000))

    print(f"🚀 Iniciando servidor en el puerto: {port}")

    # 3. Pasamos esa variable 'port' a uvicorn
    uvicorn.run(app, host="0.0.0.0", port=port)