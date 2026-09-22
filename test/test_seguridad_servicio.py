"""Pruebas del servicio de seguridad (`app.modules.seguridad.servicio`)."""
from datetime import timedelta

import pytest

from app.modules.seguridad.models import LlaveApiModel
from app.modules.seguridad.servicio import crear_llave, registrar_uso, rotar_llave, validar_llave
from app.shared.constantes import DIAS_EXPIRACION_MAXIMO_LLAVE_API
from app.shared.excepciones import AlcanceInsuficienteError, LlaveApiExpiradaError, LlaveApiInvalidaError
from app.shared.tiempo import ahora_utc


def test_crear_llave_asigna_vigencia_solicitada(db_session):
    resultado = crear_llave(
        db_session,
        sistema="power_bi",
        nombre_usuario_responsable="Equipo de BI",
        alcance="colaboradores:basico",
        dias_expiracion=30,
    )

    dias_reales = (resultado.fecha_expiracion - ahora_utc()).days
    assert 28 <= dias_reales <= 30


def test_crear_llave_no_supera_el_maximo_permitido(db_session):
    resultado = crear_llave(
        db_session,
        sistema="power_bi",
        nombre_usuario_responsable="Equipo de BI",
        alcance="colaboradores:basico",
        dias_expiracion=DIAS_EXPIRACION_MAXIMO_LLAVE_API + 100,
    )

    dias_reales = (resultado.fecha_expiracion - ahora_utc()).days
    assert dias_reales <= DIAS_EXPIRACION_MAXIMO_LLAVE_API


def test_validar_llave_exitosa_devuelve_informacion_correcta(db_session):
    resultado = crear_llave(
        db_session,
        sistema="zlhub",
        nombre_usuario_responsable="Equipo ZLHub",
        alcance="colaboradores:basico,colaboradores:costos",
    )

    info = validar_llave(db_session, clave_plana=resultado.clave_api, alcance_requerido="colaboradores:basico")

    assert info.sistema == "zlhub"
    assert info.tiene_alcance("colaboradores:costos")


def test_validar_llave_inexistente_lanza_error(db_session):
    with pytest.raises(LlaveApiInvalidaError):
        validar_llave(db_session, clave_plana="zl_no_existe", alcance_requerido="colaboradores:basico")


def test_validar_llave_sin_alcance_suficiente_lanza_error(db_session):
    """También cubre la unidireccionalidad de la jerarquía: básico nunca
    otorga costos, aunque ambos aparezcan en JERARQUIA_ALCANCES."""
    resultado = crear_llave(
        db_session, sistema="power_bi", nombre_usuario_responsable="Equipo de BI", alcance="colaboradores:basico"
    )

    with pytest.raises(AlcanceInsuficienteError):
        validar_llave(db_session, clave_plana=resultado.clave_api, alcance_requerido="colaboradores:costos")


def test_alcance_costos_por_si_solo_satisface_el_requisito_de_basico(db_session):
    """La jerarquía se expande aunque la llave solo tenga 'colaboradores:costos'
    listado en su alcance (sin 'colaboradores:basico' explícito): costos es
    un superconjunto de básico, no un permiso paralelo que haya que declarar
    dos veces. Ver JERARQUIA_ALCANCES en app.shared.constantes."""
    resultado = crear_llave(
        db_session, sistema="power_bi", nombre_usuario_responsable="Equipo de BI", alcance="colaboradores:costos"
    )

    info = validar_llave(db_session, clave_plana=resultado.clave_api, alcance_requerido="colaboradores:basico")

    assert info.tiene_alcance("colaboradores:basico")
    assert info.tiene_alcance("colaboradores:costos")


def test_validar_llave_expirada_lanza_error(db_session):
    resultado = crear_llave(
        db_session, sistema="power_bi", nombre_usuario_responsable="Equipo de BI", alcance="colaboradores:basico"
    )
    llave = db_session.query(LlaveApiModel).filter(LlaveApiModel.id == resultado.id).first()
    llave.fecha_expiracion = ahora_utc() - timedelta(days=1)
    db_session.commit()

    with pytest.raises(LlaveApiExpiradaError):
        validar_llave(db_session, clave_plana=resultado.clave_api, alcance_requerido="colaboradores:basico")


def test_registrar_uso_incrementa_contadores(db_session):
    resultado = crear_llave(
        db_session, sistema="sga", nombre_usuario_responsable="Equipo SGA", alcance="colaboradores:basico"
    )
    llave = db_session.query(LlaveApiModel).filter(LlaveApiModel.id == resultado.id).first()

    registrar_uso(db_session, llave)
    registrar_uso(db_session, llave)

    assert llave.llamados_hoy == 2
    assert llave.total_llamados == 2
    assert llave.fecha_ultimo_uso is not None


def test_rotar_llave_genera_nuevo_valor_y_reinicia_contadores(db_session):
    resultado = crear_llave(
        db_session, sistema="sga", nombre_usuario_responsable="Equipo SGA", alcance="colaboradores:basico"
    )
    llave = db_session.query(LlaveApiModel).filter(LlaveApiModel.id == resultado.id).first()
    registrar_uso(db_session, llave)

    rotada = rotar_llave(db_session, llave=llave)

    assert rotada.clave_api != resultado.clave_api
    assert llave.total_llamados == 0
    assert llave.llamados_hoy == 0

    with pytest.raises(LlaveApiInvalidaError):
        validar_llave(db_session, clave_plana=resultado.clave_api, alcance_requerido="colaboradores:basico")

    info = validar_llave(db_session, clave_plana=rotada.clave_api, alcance_requerido="colaboradores:basico")
    assert info.sistema == "sga"


def test_crear_llave_incluye_prefijo_del_sistema(db_session):
    resultado = crear_llave(
        db_session, sistema="sga", nombre_usuario_responsable="Equipo SGA", alcance="colaboradores:basico"
    )

    assert resultado.clave_api.startswith("zl-sga_")


def test_crear_llave_sistema_desconocido_usa_prefijo_generico(db_session):
    resultado = crear_llave(
        db_session, sistema="sistema_futuro", nombre_usuario_responsable="Equipo X", alcance="colaboradores:basico"
    )

    assert resultado.clave_api.startswith("zl-ext_")


def test_llave_revocada_lanza_error_con_identidad_adjunta(db_session):
    resultado = crear_llave(
        db_session, sistema="power_bi", nombre_usuario_responsable="Equipo de BI", alcance="colaboradores:basico"
    )
    llave = db_session.query(LlaveApiModel).filter(LlaveApiModel.id == resultado.id).first()
    llave.activa = False
    db_session.commit()

    with pytest.raises(LlaveApiInvalidaError) as excepcion:
        validar_llave(db_session, clave_plana=resultado.clave_api, alcance_requerido="colaboradores:basico")

    assert excepcion.value.sistema == "power_bi"
    assert excepcion.value.identificador_llave == resultado.id


def test_llave_expirada_lanza_error_con_identidad_adjunta(db_session):
    resultado = crear_llave(
        db_session, sistema="power_bi", nombre_usuario_responsable="Equipo de BI", alcance="colaboradores:basico"
    )
    llave = db_session.query(LlaveApiModel).filter(LlaveApiModel.id == resultado.id).first()
    llave.fecha_expiracion = ahora_utc() - timedelta(days=1)
    db_session.commit()

    with pytest.raises(LlaveApiExpiradaError) as excepcion:
        validar_llave(db_session, clave_plana=resultado.clave_api, alcance_requerido="colaboradores:basico")

    assert excepcion.value.sistema == "power_bi"


def test_alcance_insuficiente_lanza_error_con_identidad_adjunta(db_session):
    resultado = crear_llave(
        db_session, sistema="power_bi", nombre_usuario_responsable="Equipo de BI", alcance="colaboradores:basico"
    )

    with pytest.raises(AlcanceInsuficienteError) as excepcion:
        validar_llave(db_session, clave_plana=resultado.clave_api, alcance_requerido="colaboradores:costos")

    assert excepcion.value.sistema == "power_bi"
    assert excepcion.value.identificador_llave == resultado.id
    assert excepcion.value.responsable == "Equipo de BI"


def test_llave_inexistente_no_lleva_identidad(db_session):
    with pytest.raises(LlaveApiInvalidaError) as excepcion:
        validar_llave(db_session, clave_plana="zl-sga_no_existe", alcance_requerido="colaboradores:basico")

    assert excepcion.value.sistema is None
