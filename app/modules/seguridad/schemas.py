"""Esquemas relacionados con el ciclo de vida de una llave de API.

LlaveApiCreada es la unica ocasion en la que el valor en texto plano de la
llave existe fuera de la memoria del proceso que la genero, se entrega una
vez, por un canal seguro, y no vuelve a estar disponible después.
"""
from datetime import datetime

from pydantic import BaseModel


class LlaveApiCreada(BaseModel):
    id: int
    sistema: str
    nombre_usuario_responsable: str
    alcance: str
    fecha_expiracion: datetime
    clave_api: str
