"""Pruebas de `app.core.cors`: política de CORS distinta por prefijo de ruta.

Se usa una aplicación FastAPI mínima, aislada de la aplicación real, para no
depender de MySQL/Prosoft ni de la autenticación por API Key: lo único que
se quiere probar aquí es el comportamiento del middleware de CORS.
"""
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.cors import MiddlewareCorsPorModulo, PoliticaCorsModulo


def _construir_cliente_prueba() -> TestClient:
    app = FastAPI()

    @app.get("/api/v1/integraciones/colaboradores")
    def listar_colaboradores():
        return {"ok": True}

    @app.get("/api/v1/sga/transporte/solicitudes")
    def listar_solicitudes_transporte():
        return {"ok": True}

    @app.get("/api/v1/sga/sin-politica")
    def sin_politica():
        return {"ok": True}

    politicas = {
        "/api/v1/integraciones/colaboradores": PoliticaCorsModulo(origenes=["https://zlhub.zonalogistica.com.co"]),
        "/api/v1/sga/transporte": PoliticaCorsModulo(
            origenes=["https://sga.zonalogistica.com.co"],
            metodos=["GET", "POST"],
            encabezados=["Content-Type", "X-API-Key"],
        ),
    }
    app.add_middleware(MiddlewareCorsPorModulo, politicas=politicas)
    return TestClient(app)


def test_solicitud_sin_origin_no_es_afectada():
    """Una llamada servidor-a-servidor (sin encabezado Origin) no es una solicitud CORS."""
    cliente = _construir_cliente_prueba()

    respuesta = cliente.get("/api/v1/integraciones/colaboradores")

    assert respuesta.status_code == 200
    assert "access-control-allow-origin" not in respuesta.headers


def test_origen_autorizado_recibe_encabezado_cors():
    cliente = _construir_cliente_prueba()

    respuesta = cliente.get("/api/v1/integraciones/colaboradores", headers={"Origin": "https://zlhub.zonalogistica.com.co"})

    assert respuesta.status_code == 200
    assert respuesta.headers["access-control-allow-origin"] == "https://zlhub.zonalogistica.com.co"
    assert respuesta.headers["vary"] == "Origin"


def test_origen_no_autorizado_no_recibe_encabezado_cors():
    """El servidor sí responde (la autenticación por API Key es otra capa), pero sin
    Access-Control-Allow-Origin el navegador bloqueará la lectura desde JavaScript."""
    cliente = _construir_cliente_prueba()

    respuesta = cliente.get("/api/v1/integraciones/colaboradores", headers={"Origin": "https://otro-sitio.com"})

    assert respuesta.status_code == 200
    assert "access-control-allow-origin" not in respuesta.headers


def test_ruta_sin_politica_no_recibe_encabezados_cors():
    cliente = _construir_cliente_prueba()

    respuesta = cliente.get("/api/v1/sga/sin-politica", headers={"Origin": "https://zlhub.zonalogistica.com.co"})

    assert respuesta.status_code == 200
    assert "access-control-allow-origin" not in respuesta.headers


def test_politica_de_un_modulo_no_aplica_de_forma_cruzada_a_otro():
    cliente = _construir_cliente_prueba()

    # El origen autorizado para /api/v1/sga/transporte no debe funcionar contra /api/v1/integraciones/colaboradores.
    respuesta = cliente.get("/api/v1/integraciones/colaboradores", headers={"Origin": "https://sga.zonalogistica.com.co"})

    assert "access-control-allow-origin" not in respuesta.headers


def test_preflight_exitoso():
    cliente = _construir_cliente_prueba()

    respuesta = cliente.options(
        "/api/v1/sga/transporte/solicitudes",
        headers={
            "Origin": "https://sga.zonalogistica.com.co",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type, x-api-key",
        },
    )

    assert respuesta.status_code == 200
    assert respuesta.headers["access-control-allow-origin"] == "https://sga.zonalogistica.com.co"
    assert "POST" in respuesta.headers["access-control-allow-methods"]


def test_preflight_con_origen_no_autorizado_es_rechazado():
    cliente = _construir_cliente_prueba()

    respuesta = cliente.options(
        "/api/v1/sga/transporte/solicitudes",
        headers={"Origin": "https://otro-sitio.com", "Access-Control-Request-Method": "POST"},
    )

    assert respuesta.status_code == 400


def test_preflight_con_metodo_no_permitido_es_rechazado():
    cliente = _construir_cliente_prueba()

    respuesta = cliente.options(
        "/api/v1/integraciones/colaboradores",
        headers={"Origin": "https://zlhub.zonalogistica.com.co", "Access-Control-Request-Method": "DELETE"},
    )

    assert respuesta.status_code == 400


def test_preflight_con_encabezado_no_permitido_es_rechazado():
    cliente = _construir_cliente_prueba()

    respuesta = cliente.options(
        "/api/v1/sga/transporte/solicitudes",
        headers={
            "Origin": "https://sga.zonalogistica.com.co",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "x-un-encabezado-no-declarado",
        },
    )

    assert respuesta.status_code == 400


def test_no_se_admite_comodin_como_origen():
    with pytest.raises(ValueError):
        PoliticaCorsModulo(origenes=["*"])
