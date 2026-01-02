-- Script de migración para eliminar el campo email de la tabla users
-- Ejecuta este script SOLO si ya tienes la tabla creada con el campo email
-- y quieres actualizarla para usar solo username

-- 1. Eliminar el índice en email (si existe)
DROP INDEX IF EXISTS idx_users_email;

-- 2. Eliminar la columna email
ALTER TABLE users DROP COLUMN IF EXISTS email;

-- 3. Asegurar que username sea UNIQUE (por si no lo era antes)
-- Si ya es UNIQUE, este comando no hará nada
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint 
        WHERE conname = 'users_username_key'
    ) THEN
        ALTER TABLE users ADD CONSTRAINT users_username_key UNIQUE (username);
    END IF;
END $$;

-- 4. Crear índice en username para búsquedas rápidas
CREATE INDEX IF NOT EXISTS idx_users_username ON users(username);

-- 5. Verificar la estructura final
SELECT column_name, data_type, is_nullable 
FROM information_schema.columns 
WHERE table_name = 'users' 
ORDER BY ordinal_position;

