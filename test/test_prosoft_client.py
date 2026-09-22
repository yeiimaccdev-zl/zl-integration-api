"""Pruebas del cliente de Prosoft (`app.integraciones.prosoft.client`).

Solo se prueba la lógica pura (traducción del filtro de estado), que no
requiere una conexión real a la base de datos.
"""
import pytest

from app.integraciones.prosoft.client import traducir_estado
from app.shared.excepciones import ParametroInvalidoError


def test_traducir_estado_activo():
    assert traducir_estado("ACTIVO") == 1


def test_traducir_estado_inactivo_es_insensible_a_mayusculas():
    assert traducir_estado("inactivo") == 0


def test_traducir_estado_nulo_no_filtra():
    assert traducir_estado(None) is None


def test_traducir_estado_invalido_lanza_error():
    with pytest.raises(ParametroInvalidoError):
        traducir_estado("RETIRADO")
