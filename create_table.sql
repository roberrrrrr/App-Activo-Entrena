-- Script SQL para crear la tabla users en PostgreSQL
-- Ejecuta este script en tu base de datos antes de usar el backend

-- Crear la base de datos (si no existe)
-- CREATE DATABASE flutter_app_db;

-- Conectarse a la base de datos
-- \c flutter_app_db;

-- Crear la tabla users
CREATE TABLE IF NOT EXISTS users (
    id SERIAL PRIMARY KEY,
    username VARCHAR(100) UNIQUE NOT NULL,
    password VARCHAR(255) NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Crear índice en username para búsquedas rápidas
CREATE INDEX IF NOT EXISTS idx_users_username ON users(username);

-- Insertar un usuario de prueba (opcional)
-- IMPORTANTE: En producción, NUNCA guardes contraseñas en texto plano
-- Usa funciones de hash como bcrypt o argon2
INSERT INTO users (username, password) 
VALUES ('usuario_test', 'password123')
ON CONFLICT (username) DO NOTHING;

-- Verificar que se creó correctamente
SELECT * FROM users;

