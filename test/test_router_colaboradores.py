"""Pruebas de integración de los endpoints de colaboradores.

Incluyen, de forma deliberada, verificación directa sobre la tabla de
auditoría: no basta con que el endpoint responda el código HTTP correcto,
también debe quedar completamente trazado, incluso cuando la solicitud es
rechazada.
"""
from fastapi.testclient import TestClient

import app.integraciones.prosoft.router as router_colaboradores
from app.core.database import get_db
from app.main import app
from app.modules.auditoria.models import RegistroAuditoriaModel
from app.modules.seguridad.servicio import crear_llave
from app.shared.constantes import CATEGORIA_ERROR_AUTENTICACION, CATEGORIA_ERROR_AUTORIZACION

FILA_COLABORADOR_PRUEBA = {
    "cedula": "123",
    "nombre_completo": "KEVIN PRUEBA",
    "correos": "",
    "cargo": "Analista",
    "telefono": "",
    "celular": "",
    "fecha_ingreso": "2024-01-01",
    "fecha_retiro": "",
    "estado": "Activo",
    "gerencia": "",
    "sede": "",
    "division": "",
    "area_departamento": "",
    "salario": "3000000",
    "auxilio_transporte": "150000",
}


def _crear_cliente(db_session, monkeypatch, filas=None):
    filas_a_devolver = filas if filas is not None else [FILA_COLABORADOR_PRUEBA]
    monkeypatch.setattr(router_colaboradores, "consultar_colaboradores", lambda **kwargs: filas_a_devolver)
    app.dependency_overrides[get_db] = lambda: (yield db_session)
    return TestClient(app, raise_server_exceptions=False)


def _ultimo_registro_auditoria(db_session) -> RegistroAuditoriaModel:
    return db_session.query(RegistroAuditoriaModel).order_by(RegistroAuditoriaModel.id.desc()).first()


def test_listado_sin_alcance_de_costos_no_incluye_salario(db_session, monkeypatch):
    cliente = _crear_cliente(db_session, monkeypatch)
    resultado = crear_llave(
        db_session, sistema="power_bi", nombre_usuario_responsable="Equipo de BI", alcance="colaboradores:basico"
    )

    respuesta = cliente.get("/api/v1/integraciones/colaboradores", headers={"X-API-Key": resultado.clave_api})

    assert respuesta.status_code == 200
    assert "salario" not in respuesta.json()[0]

    registro = _ultimo_registro_auditoria(db_session)
    assert registro.sistema_consumidor == "power_bi"
    assert registro.cantidad_registros == 1
    assert registro.tamano_respuesta_bytes is not None and registro.tamano_respuesta_bytes > 0


def test_detalle_con_alcance_de_costos_incluye_salario(db_session, monkeypatch):
    cliente = _crear_cliente(db_session, monkeypatch)
    resultado = crear_llave(
        db_session,
        sistema="sga",
        nombre_usuario_responsable="Equipo SGA",
        alcance="colaboradores:basico,colaboradores:costos",
    )

    respuesta = cliente.get("/api/v1/integraciones/colaboradores/123", headers={"X-API-Key": resultado.clave_api})

    assert respuesta.status_code == 200
    assert respuesta.json()["salario"] == "3000000"


def test_listado_con_solo_alcance_de_costos_pasa_el_minimo_de_basico_e_incluye_salario(db_session, monkeypatch):
    """El endpoint de listado exige ALCANCE_COLABORADORES_BASICO como mínimo
    (ver requerir_alcance_minimo). Una llave creada con únicamente
    'colaboradores:costos' en la base de datos —sin 'colaboradores:basico'
    listado explícitamente— también pasa esa validación, porque costos es
    un superconjunto de básico (JERARQUIA_ALCANCES), y además recibe el
    listado con salario incluido, porque mapear_colaborador() decide el
    payload a partir del alcance real de la llave, no del alcance mínimo
    exigido por la ruta."""
    cliente = _crear_cliente(db_session, monkeypatch)
    resultado = crear_llave(
        db_session, sistema="power_bi", nombre_usuario_responsable="Equipo de BI", alcance="colaboradores:costos"
    )

    respuesta = cliente.get("/api/v1/integraciones/colaboradores", headers={"X-API-Key": resultado.clave_api})

    assert respuesta.status_code == 200
    assert respuesta.json()[0]["salario"] == "3000000"


def test_sin_api_key_devuelve_401_y_no_deja_prefijo(db_session, monkeypatch):
    cliente = _crear_cliente(db_session, monkeypatch)

    respuesta = cliente.get("/api/v1/integraciones/colaboradores")

    assert respuesta.status_code == 401

    registro = _ultimo_registro_auditoria(db_session)
    assert registro.sistema_consumidor is None
    assert registro.prefijo_llave_intentada is None  # no se envió ningún encabezado que enmascarar
    assert registro.categoria_error == CATEGORIA_ERROR_AUTENTICACION
    assert registro.mensaje_error == "Se requiere una API Key en el encabezado 'X-API-Key'"


def test_llave_inexistente_deja_prefijo_enmascarado(db_session, monkeypatch):
    cliente = _crear_cliente(db_session, monkeypatch)

    respuesta = cliente.get("/api/v1/integraciones/colaboradores", headers={"X-API-Key": "zl-sga_intento-de-ataque"})

    assert respuesta.status_code == 401

    registro = _ultimo_registro_auditoria(db_session)
    assert registro.sistema_consumidor is None
    assert registro.prefijo_llave_intentada.startswith("zl-sga_")
    assert len(registro.prefijo_llave_intentada) <= 20
    assert registro.categoria_error == CATEGORIA_ERROR_AUTENTICACION


def test_costos_sin_alcance_suficiente_devuelve_403_y_conserva_identidad(db_session, monkeypatch):
    """Este es el caso que motivó la corrección: un 403 ya no debe dejar la
    identidad del sistema consumidor en null."""
    cliente = _crear_cliente(db_session, monkeypatch)
    resultado = crear_llave(
        db_session, sistema="power_bi", nombre_usuario_responsable="Equipo de BI", alcance="colaboradores:basico"
    )

    respuesta = cliente.get(
        "/api/v1/integraciones/colaboradores/123/costos", headers={"X-API-Key": resultado.clave_api}
    )

    assert respuesta.status_code == 403

    registro = _ultimo_registro_auditoria(db_session)
    assert registro.sistema_consumidor == "power_bi"
    assert registro.identificador_llave_api == resultado.id
    assert registro.responsable_llave_api == "Equipo de BI"
    assert registro.categoria_error == CATEGORIA_ERROR_AUTORIZACION
    assert registro.mensaje_error == "Se requiere el alcance 'colaboradores:costos'"


def test_colaborador_no_encontrado_devuelve_404_con_mensaje_auditado(db_session, monkeypatch):
    cliente = _crear_cliente(db_session, monkeypatch, filas=[])
    resultado = crear_llave(
        db_session, sistema="power_bi", nombre_usuario_responsable="Equipo de BI", alcance="colaboradores:basico"
    )

    respuesta = cliente.get("/api/v1/integraciones/colaboradores/999", headers={"X-API-Key": resultado.clave_api})

    assert respuesta.status_code == 404

    registro = _ultimo_registro_auditoria(db_session)
    assert registro.sistema_consumidor == "power_bi"
    assert registro.mensaje_error == "No se encontró un colaborador con cédula 999"


def test_encabezado_x_forwarded_for_se_registra_como_ip_real(db_session, monkeypatch):
    cliente = _crear_cliente(db_session, monkeypatch)
    resultado = crear_llave(
        db_session, sistema="power_bi", nombre_usuario_responsable="Equipo de BI", alcance="colaboradores:basico"
    )

    cliente.get(
        "/api/v1/integraciones/colaboradores",
        headers={"X-API-Key": resultado.clave_api, "X-Forwarded-For": "203.0.113.9, 10.0.0.1"},
    )

    registro = _ultimo_registro_auditoria(db_session)
    assert registro.ip_origen == "203.0.113.9"
    assert registro.ip_real_cliente == "203.0.113.9, 10.0.0.1"
