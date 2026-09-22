""" Capa anticorrupcion del modulo Prosoft.

Traduce las filas crudas obtenidas de client.py al esquema de salida que
corresponde segun el alcance del sistema consumidor.
"""
from app.integraciones.prosoft.schemas import ColaboradorBasico, ColaboradorCostos
from app.shared.constantes import ALCANCE_COLABORADORES_COSTOS


def mapear_colaborador(fila: dict, alcances: list[str]) -> ColaboradorBasico | ColaboradorCostos:
    """ Construye el esquema de colaborador adecuado segun los alcances disponibles. """
    if ALCANCE_COLABORADORES_COSTOS in alcances:
        return ColaboradorCostos(**fila)
    return ColaboradorBasico(**fila)
