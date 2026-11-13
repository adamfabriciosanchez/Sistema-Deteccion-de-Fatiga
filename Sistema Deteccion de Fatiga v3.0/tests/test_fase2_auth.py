"""
Script de verificación automatizada para la Fase 2: Autenticación JWT, RBAC y Vistas Web
"""
import sys
import os

# Asegurar que el path del proyecto está disponible
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi.testclient import TestClient
from main import app
from app.core.dependencies import require_roles
from app.models.models import RolUsuario
from fastapi import APIRouter, Depends

# Agregar un endpoint de prueba para validar RBAC estricto
test_rbac_router = APIRouter()
@test_rbac_router.get("/test-solo-admin")
def endpoint_solo_admin(user=Depends(require_roles([RolUsuario.ADMIN]))):
    return {"message": f"Autorizado como Administrador: {user.email}"}

app.include_router(test_rbac_router)

client = TestClient(app)

def test_fase2():
    print("=================================================================")
    print("  EJECUTANDO PRUEBAS DE LA FASE 2: AUTENTICACIÓN Y VISTAS WEB    ")
    print("=================================================================")

    # 1. Prueba de inicio de sesión vía API REST para los 3 roles
    print("\n[1/5] Probando autenticación REST (POST /api/v1/auth/login)...")
    
    # 1.1 Login Admin
    res_admin = client.post("/api/v1/auth/login", json={"email": "admin@transcopacabana.com", "password": "123456"})
    assert res_admin.status_code == 200, f"Error login admin: {res_admin.text}"
    token_admin = res_admin.json()["access_token"]
    assert res_admin.json()["rol"] == "ADMIN"
    print(f" -> Login ADMIN exitoso. Token generado: {token_admin[:20]}...")

    # 1.2 Login Operador
    res_operador = client.post("/api/v1/auth/login", json={"email": "operador@transcopacabana.com", "password": "123456"})
    assert res_operador.status_code == 200, f"Error login operador: {res_operador.text}"
    token_operador = res_operador.json()["access_token"]
    assert res_operador.json()["rol"] == "OPERADOR"
    print(f" -> Login OPERADOR exitoso. Token generado: {token_operador[:20]}...")

    # 1.3 Login Conductor
    res_conductor = client.post("/api/v1/auth/login", json={"email": "carlos@conductor.com", "password": "123456"})
    assert res_conductor.status_code == 200, f"Error login conductor: {res_conductor.text}"
    token_conductor = res_conductor.json()["access_token"]
    assert res_conductor.json()["rol"] == "CONDUCTOR"
    print(f" -> Login CONDUCTOR exitoso. Token generado: {token_conductor[:20]}...")

    # 1.4 Login Fallido
    res_fail = client.post("/api/v1/auth/login", json={"email": "admin@transcopacabana.com", "password": "clave_incorrecta"})
    assert res_fail.status_code == 401
    print(" -> Rechazo con HTTP 401 ante contraseña errónea validado.")

    # 2. Prueba de Endpoint Protegido (/api/v1/auth/me)
    print("\n[2/5] Probando endpoint protegido (GET /api/v1/auth/me)...")
    res_me_unauth = client.get("/api/v1/auth/me")
    assert res_me_unauth.status_code == 401
    print(" -> Rechazo HTTP 401 sin token validado.")

    res_me_admin = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token_admin}"})
    assert res_me_admin.status_code == 200
    assert res_me_admin.json()["email"] == "admin@transcopacabana.com"
    print(f" -> Perfil obtenido exitosamente para: {res_me_admin.json()['nombre']} {res_me_admin.json()['apellido']}")

    # 3. Control de Acceso por Roles (RBAC)
    print("\n[3/5] Probando Control de Acceso Basado en Roles (RBAC)...")
    # Conductor intentando acceder a ruta solo admin -> debe dar 403 Forbidden
    res_rbac_forbidden = client.get("/test-solo-admin", headers={"Authorization": f"Bearer {token_conductor}"})
    assert res_rbac_forbidden.status_code == 403, f"Esperado 403, obtenido {res_rbac_forbidden.status_code}"
    print(" -> Acceso denegado (HTTP 403) a Conductor en endpoint de Administrador validado.")

    # Admin accediendo a ruta solo admin -> debe dar 200 OK
    res_rbac_ok = client.get("/test-solo-admin", headers={"Authorization": f"Bearer {token_admin}"})
    assert res_rbac_ok.status_code == 200
    print(" -> Acceso permitido (HTTP 200) a Administrador validado.")

    # 4. Vistas Web (Jinja2 + Bootstrap 5 estilo Docente)
    print("\n[4/5] Probando vistas web del docente (GET / y GET /login)...")
    res_home = client.get("/")
    assert res_home.status_code == 200
    assert "TRANS COPACABANA" in res_home.text
    print(" -> Vista '/' (home.html) renderizada con branding Trans Copacabana.")

    res_login_view = client.get("/login")
    assert res_login_view.status_code == 200
    assert "Control de Acceso" in res_login_view.text
    print(" -> Vista '/login' (login.html) renderizada con formulario de acceso.")

    # 5. Flujo Web Completo: Login Formulario -> Cookie de Sesión -> Dashboard -> Logout
    print("\n[5/5] Probando flujo web completo (Form Login -> Cookie -> Dashboard -> Logout)...")
    res_web_login = client.post(
        "/login",
        data={"email": "admin@transcopacabana.com", "password": "123456"},
        follow_redirects=False
    )
    assert res_web_login.status_code == 303
    assert "access_token" in res_web_login.cookies
    print(" -> Formulario Web de login generó cookie 'access_token' y redirigió a /dashboard.")

    # Acceso a /dashboard usando la cookie de sesión
    res_dashboard = client.get("/dashboard", cookies=res_web_login.cookies)
    assert res_dashboard.status_code == 200
    assert "Panel de Control Operativo" in res_dashboard.text
    print(" -> Acceso a /dashboard exitoso utilizando sesión basada en cookies.")

    # Logout
    res_logout = client.get("/logout", follow_redirects=False)
    assert res_logout.status_code == 302
    print(" -> Cierre de sesión (GET /logout) ejecutado con éxito.")

    print("\n=================================================================")
    print("  RESULTADO: TODAS LAS PRUEBAS DE LA FASE 2 PASARON CON ÉXITO    ")
    print("=================================================================")

if __name__ == "__main__":
    test_fase2()
