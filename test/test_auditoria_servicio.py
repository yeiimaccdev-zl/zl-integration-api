"""Pruebas del servicio de auditoría (`app.modules.auditoria.servicio`)."""
from app.modules.auditoria.models import RegistroAuditoriaModel
from app.modules.auditoria.servicio import registrar_solicitud
from app.shared.constantes import CATEGORIA_ERROR_AUTORIZACION
from app.shared.tiempo import ahora_utc


def _registrar(db_session, **overrides):
    base = dict(
        identificador_solicitud="11111111-1111-1111-1111-111111111111",
        servicio="zl-integration-api",
        metodo_http="GET",
        ruta="/colaboradores",
        parametros_consulta="nombre=KEVIN",
        sistema_consumidor="power_bi",
        identificador_llave_api=1,
        responsable_llave_api="Equipo de BI",
        prefijo_llave_intentada=None,
        ip_origen="10.0.0.5",
        ip_real_cliente=None,
        agente_usuario="pytest",
        codigo_respuesta=200,
        duracion_ms=123.45,
        tamano_respuesta_bytes=512,
        cantidad_registros=3,
        categoria_error=None,
        mensaje_error=None,
        fecha_hora_inicio=ahora_utc(),
    )
    base.update(overrides)
    registrar_solicitud(db_session, **base)


def test_registrar_solicitud_guarda_todos_los_campos_esperados(db_session):
    _registrar(db_session)

    registro = db_session.query(RegistroAuditoriaModel).one()

    assert registro.servicio == "zl-integration-api"
    assert registro.sistema_consumidor == "power_bi"
    assert registro.responsable_llave_api == "Equipo de BI"
    assert registro.exitosa is True
    assert registro.codigo_respuesta == 200
    assert registro.cantidad_registros == 3
    assert registro.tamano_respuesta_bytes == 512


def test_registrar_solicitud_marca_no_exitosa_en_error(db_session):
    _registrar(
        db_session,
        identificador_solicitud="22222222-2222-2222-2222-222222222222",
        codigo_respuesta=403,
        categoria_error=CATEGORIA_ERROR_AUTORIZACION,
        mensaje_error="Se requiere el alcance 'colaboradores:costos'",
    )

    registro = db_session.query(RegistroAuditoriaModel).one()

    assert registro.exitosa is False
    assert registro.categoria_error == CATEGORIA_ERROR_AUTORIZACION
    assert registro.mensaje_error == "Se requiere el alcance 'colaboradores:costos'"


def test_registrar_solicitud_admite_prefijo_de_llave_sin_identidad(db_session):
    """Caso de una llave que no llegó a identificarse: solo queda el prefijo saneado."""
    _registrar(
        db_session,
        identificador_solicitud="33333333-3333-3333-3333-333333333333",
        sistema_consumidor=None,
        identificador_llave_api=None,
        responsable_llave_api=None,
        prefijo_llave_intentada="zl-sga_a1b",
        codigo_respuesta=401,
        categoria_error="AUTENTICACION",
        mensaje_error="La API Key no existe",
    )

    registro = db_session.query(RegistroAuditoriaModel).one()

    assert registro.sistema_consumidor is None
    assert registro.prefijo_llave_intentada == "zl-sga_a1b"
