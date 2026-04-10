# Gym Tracking & Management App 🏃‍♂️📱

Aplicación móvil de alto rendimiento para el seguimiento de actividad física y gestión de comunidades deportivas.

### 🌟 Características Principales
- **Tracking GPS:** Sincronización de rutas y actividades.
- **Integración con Strava:** Implementación de flujo **OAuth2** para sincronización de datos de terceros.
- **Gamificación:** Rankings en tiempo real basados en el rendimiento de los socios.

### 🛠️ Stack Tecnológico
- **Mobile:** Flutter (Dart).
- **API Backend:** Python (FastAPI).
- **Base de Datos:** PostgreSQL con funciones de ventana para analítica.
- **Infraestructura:** Railway (HTTPS, Enrutamiento de dominios).

### 🧠 Ingeniería Aplicada
- **Suavizado de GPS:** Desarrollo de algoritmos de decimación de puntos para optimizar la visualización de rutas en mapas y reducir el almacenamiento en DB.
- **Automatización:** Tareas en segundo plano con **APScheduler** para cierres de temporada y procesamiento de datos.


# Backend Flutter App - FastAPI + PostgreSQL

Backend API para la aplicación Flutter que maneja autenticación y se conecta a PostgreSQL.

## 📋 Requisitos Previos

- Python 3.8 o superior
- PostgreSQL instalado y corriendo localmente
- pip (gestor de paquetes de Python)

## 🚀 Instalación

### 1. Instalar dependencias de Python

```bash
cd backend
pip install -r requirements.txt
```

O instala manualmente:

```bash
pip install fastapi uvicorn[standard] psycopg2-binary pydantic python-multipart
```

### 2. Configurar PostgreSQL

1. **Crea la base de datos:**
   ```sql
   CREATE DATABASE flutter_app_db;
   ```

2. **Ejecuta el script SQL para crear la tabla:**
   ```bash
   psql -U postgres -d flutter_app_db -f create_table.sql
   ```
   
   O ejecuta manualmente en psql:
   ```sql
   \c flutter_app_db
   \i create_table.sql
   ```
   
   **Nota:** Si ya tienes una tabla `users` con el campo `email` de una versión anterior, ejecuta primero el script de migración:
   ```bash
   psql -U postgres -d flutter_app_db -f migrate_remove_email.sql
   ```

3. **Configura las credenciales en `config.py`:**
   ```python
   DB_CONFIG = {
       "host": "localhost",
       "port": 5432,
       "database": "flutter_app_db",
       "user": "tu_usuario",      # ← Cambia esto
       "password": "tu_password",  # ← Cambia esto
   }
   ```

## ▶️ Ejecutar el Servidor

### Opción 1: Usando uvicorn directamente
```bash
cd backend
uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

### Opción 2: Usando Python
```bash
cd backend
python main.py
```

El servidor estará disponible en:
- **Local:** http://localhost:8000
- **Emulador Android:** http://10.0.2.2:8000
- **Dispositivo físico:** http://[IP_DE_TU_PC]:8000

## 📡 Endpoints

### GET `/`
Endpoint de prueba para verificar que el servidor está funcionando.

### POST `/api/auth/login`
Endpoint de login que valida credenciales.

**Request:**
```json
{
  "userName": "usuario_test",
  "password": "password123"
}
```

**Response (éxito):**
```json
{
  "success": true,
  "message": "Login exitoso",
  "user": {
    "id": "1",
    "username": "usuario_test"
  }
}
```

**Response (error 401):**
```json
{
  "detail": "Credenciales inválidas"
}
```

### GET `/api/health`
Verifica el estado del servidor y la conexión a la base de datos.

## 🔧 Configuración para Flutter

En `flutter_application_1/lib/config/app_config.dart`, actualiza:

```dart
static String get apiBaseUrl {
  switch (environment) {
    case AppEnvironment.local:
      // Para emulador Android
      return 'http://10.0.2.2:8000/api';
      // O para dispositivo físico, usa la IP de tu PC
      // return 'http://192.168.1.100:8000/api';
    ...
  }
}
```

Y cambia:
```dart
static const bool useMockData = false; // ← Cambia a false
```

## ⚠️ Notas de Seguridad

1. **Contraseñas:** Actualmente las contraseñas se comparan en texto plano. En producción, DEBES usar:
   - Hashing con bcrypt o argon2
   - Nunca almacenar contraseñas en texto plano

2. **CORS:** El middleware CORS está configurado para permitir todos los orígenes (`allow_origins=["*"]`). En producción, especifica los orígenes exactos.

3. **Variables de entorno:** Considera usar un archivo `.env` para las credenciales de la base de datos en lugar de hardcodearlas.

## 🐛 Solución de Problemas

### Error: "No module named 'psycopg2'"
```bash
pip install psycopg2-binary
```

### Error: "Connection refused" o "No se pudo conectar"
- Verifica que PostgreSQL esté corriendo
- Verifica las credenciales en `config.py`
- Verifica que el puerto 5432 esté abierto

### Error desde Flutter: "No se pudo conectar con el servidor"
- Verifica que el servidor esté corriendo
- Para emulador Android, usa `10.0.2.2` en lugar de `localhost`
- Para dispositivo físico, usa la IP de tu PC en la misma red WiFi

