"""Pruebas del punto de entrada (`app.main`): health check con dependencias
reales y restricción de la documentación interactiva según el entorno."""
from fastapi.testclient import TestClient

import app.main as main_modulo
from app.main import _resolver_urls_documentacion, app


def test_docs_deshabilitados_en_produccion():
    assert _resolver_urls_documentacion(es_produccion=True) == (None, None, None)


def test_docs_habilitados_en_desarrollo():
    assert _resolver_urls_documentacion(es_produccion=False) == ("/docs", "/redoc", "/openapi.json")


def test_health_check_saludable_devuelve_200(monkeypatch):
    monkeypatch.setattr(main_modulo, "verificar_conexion_mysql", lambda: True)
    monkeypatch.setattr(main_modulo, "verificar_conexion_prosoft", lambda: True)
    cliente = TestClient(app, raise_server_exceptions=False)

    respuesta = cliente.get("/health")

    assert respuesta.status_code == 200
    cuerpo = respuesta.json()
    assert cuerpo["status"] == "ok"
    assert cuerpo["mysql"] == "arriba"
    assert cuerpo["prosoft"] == "arriba"


def test_health_check_degradado_si_prosoft_no_responde(monkeypatch):
    monkeypatch.setattr(main_modulo, "verificar_conexion_mysql", lambda: True)
    monkeypatch.setattr(main_modulo, "verificar_conexion_prosoft", lambda: False)
    cliente = TestClient(app, raise_server_exceptions=False)

    respuesta = cliente.get("/health")

    assert respuesta.status_code == 503
    assert respuesta.json()["prosoft"] == "no_disponible"


def test_cabeceras_de_seguridad_presentes_en_toda_respuesta(monkeypatch):
    monkeypatch.setattr(main_modulo, "verificar_conexion_mysql", lambda: True)
    monkeypatch.setattr(main_modulo, "verificar_conexion_prosoft", lambda: True)
    cliente = TestClient(app, raise_server_exceptions=False)

    respuesta = cliente.get("/health")

    assert respuesta.headers["X-Content-Type-Options"] == "nosniff"
    assert respuesta.headers["X-Frame-Options"] == "DENY"
    assert "Strict-Transport-Security" in respuesta.headers
