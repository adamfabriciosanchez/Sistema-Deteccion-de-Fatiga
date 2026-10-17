-- ===============================================================================
-- SEED DATA PARA TRANS COPACABANA (DATOS DE PRUEBA)
-- ===============================================================================

-- Limpiar tablas
TRUNCATE TABLE rol CASCADE;
TRUNCATE TABLE usuario CASCADE;
TRUNCATE TABLE vehiculo CASCADE;

-- Insertar Roles
INSERT INTO rol (id, nombre, descripcion) VALUES
(1, 'ADMIN', 'Administrador del sistema con acceso total'),
(2, 'OPERADOR', 'Operador de monitoreo y despacho'),
(3, 'CONDUCTOR', 'Conductor de flota');

-- Usaremos un hash dummy de bcrypt para '123456': $2b$12$cM08kNV9TPiZkOaI88n4Ku1W5qKH9Y3vUDky.06vVJKpdHiVcOVre
-- Así podrán iniciar sesión si el sistema valida bcrypt.

-- Insertar Usuarios (Admin y Operador)
INSERT INTO usuario (id, ci, nombre, apellido, email, password_hash, rol_id, estado) VALUES
('a0000000-0000-0000-0000-000000000001', '1234567', 'Juan', 'Perez (Admin)', 'admin@transcopacabana.com', '$2b$12$cM08kNV9TPiZkOaI88n4Ku1W5qKH9Y3vUDky.06vVJKpdHiVcOVre', 1, TRUE),
('a0000000-0000-0000-0000-000000000002', '7654321', 'Maria', 'Gomez (Operador)', 'operador@transcopacabana.com', '$2b$12$cM08kNV9TPiZkOaI88n4Ku1W5qKH9Y3vUDky.06vVJKpdHiVcOVre', 2, TRUE);

-- Insertar Conductores
-- Conductor 1: Cochabamba
INSERT INTO usuario (id, ci, nombre, apellido, email, password_hash, rol_id) VALUES
('c0000000-0000-0000-0000-000000000001', '5550001', 'Carlos', 'Mamani', 'carlos@conductor.com', '$2b$12$cM08kNV9TPiZkOaI88n4Ku1W5qKH9Y3vUDky.06vVJKpdHiVcOVre', 3);
INSERT INTO conductor (id, licencia_conducir, categoria_licencia, telefono_emergencia, puntaje_promedio, ubicacion_actual) VALUES
('c0000000-0000-0000-0000-000000000001', 'LIC-5550001', 'C', '77700001', 4.8, 'Cochabamba');

-- Conductor 2: La Paz
INSERT INTO usuario (id, ci, nombre, apellido, email, password_hash, rol_id) VALUES
('c0000000-0000-0000-0000-000000000002', '5550002', 'Roberto', 'Condori', 'roberto@conductor.com', '$2b$12$cM08kNV9TPiZkOaI88n4Ku1W5qKH9Y3vUDky.06vVJKpdHiVcOVre', 3);
INSERT INTO conductor (id, licencia_conducir, categoria_licencia, telefono_emergencia, puntaje_promedio, ubicacion_actual) VALUES
('c0000000-0000-0000-0000-000000000002', 'LIC-5550002', 'C', '77700002', 4.5, 'La Paz');

-- Conductor 3: Santa Cruz
INSERT INTO usuario (id, ci, nombre, apellido, email, password_hash, rol_id) VALUES
('c0000000-0000-0000-0000-000000000003', '5550003', 'Julio', 'Rojas', 'julio@conductor.com', '$2b$12$cM08kNV9TPiZkOaI88n4Ku1W5qKH9Y3vUDky.06vVJKpdHiVcOVre', 3);
INSERT INTO conductor (id, licencia_conducir, categoria_licencia, telefono_emergencia, puntaje_promedio, ubicacion_actual) VALUES
('c0000000-0000-0000-0000-000000000003', 'LIC-5550003', 'C', '77700003', 4.9, 'Santa Cruz');

-- Conductor 4: Sucre
INSERT INTO usuario (id, ci, nombre, apellido, email, password_hash, rol_id) VALUES
('c0000000-0000-0000-0000-000000000004', '5550004', 'Miguel', 'Arias', 'miguel@conductor.com', '$2b$12$cM08kNV9TPiZkOaI88n4Ku1W5qKH9Y3vUDky.06vVJKpdHiVcOVre', 3);
INSERT INTO conductor (id, licencia_conducir, categoria_licencia, telefono_emergencia, puntaje_promedio, ubicacion_actual) VALUES
('c0000000-0000-0000-0000-000000000004', 'LIC-5550004', 'C', '77700004', 5.0, 'Sucre');

-- Conductor 5: Cochabamba (Relevo)
INSERT INTO usuario (id, ci, nombre, apellido, email, password_hash, rol_id) VALUES
('c0000000-0000-0000-0000-000000000005', '5550005', 'Fernando', 'Choque', 'fernando@conductor.com', '$2b$12$cM08kNV9TPiZkOaI88n4Ku1W5qKH9Y3vUDky.06vVJKpdHiVcOVre', 3);
INSERT INTO conductor (id, licencia_conducir, categoria_licencia, telefono_emergencia, puntaje_promedio, ubicacion_actual) VALUES
('c0000000-0000-0000-0000-000000000005', 'LIC-5550005', 'C', '77700005', 4.7, 'Cochabamba');

-- Conductor 6: La Paz (Relevo)
INSERT INTO usuario (id, ci, nombre, apellido, email, password_hash, rol_id) VALUES
('c0000000-0000-0000-0000-000000000006', '5550006', 'Andres', 'Flores', 'andres@conductor.com', '$2b$12$cM08kNV9TPiZkOaI88n4Ku1W5qKH9Y3vUDky.06vVJKpdHiVcOVre', 3);
INSERT INTO conductor (id, licencia_conducir, categoria_licencia, telefono_emergencia, puntaje_promedio, ubicacion_actual) VALUES
('c0000000-0000-0000-0000-000000000006', 'LIC-5550006', 'C', '77700006', 4.6, 'La Paz');

-- Insertar Buses
INSERT INTO vehiculo (id, placa, numero_interno, marca, modelo, chasis, carroceria, capacidad_pasajeros, tipo_bus, anio_fabricacion, kilometraje_actual, fecha_ultimo_mantenimiento, soat_vigencia, ubicacion_actual) VALUES
('b0000000-0000-0000-0000-000000000001', '1234ABC', 'TC-001', 'Mercedes-Benz', 'O500RSD', 'MB-101', 'Marcopolo G7', 43, 'CAMA', 2018, 150000, '2026-09-01', '2027-01-01', 'Cochabamba'),
('b0000000-0000-0000-0000-000000000002', '2345BCD', 'TC-002', 'Volvo', 'B430R', 'VO-202', 'Marcopolo G8', 43, 'CAMA', 2020, 90000, '2026-09-15', '2027-01-01', 'La Paz'),
('b0000000-0000-0000-0000-000000000003', '3456CDE', 'TC-003', 'Scania', 'K440', 'SC-303', 'Irizar i6', 50, 'SEMI_CAMA', 2019, 120000, '2026-08-20', '2027-01-01', 'Santa Cruz'),
('b0000000-0000-0000-0000-000000000004', '4567DEF', 'TC-004', 'Mercedes-Benz', 'O500RS', 'MB-104', 'Busscar Vissta', 50, 'SEMI_CAMA', 2017, 180000, '2026-09-10', '2027-01-01', 'Sucre'),
('b0000000-0000-0000-0000-000000000005', '5678EFG', 'TC-005', 'Volvo', 'B380R', 'VO-205', 'Marcopolo G7', 43, 'LEITO', 2021, 50000, '2026-09-20', '2027-01-01', 'Cochabamba'),
('b0000000-0000-0000-0000-000000000006', '6789FGH', 'TC-006', 'Scania', 'K400', 'SC-306', 'Comil Campione', 50, 'SEMI_CAMA', 2018, 140000, '2026-08-15', '2027-01-01', 'La Paz');

-- Fin de Seed Data
