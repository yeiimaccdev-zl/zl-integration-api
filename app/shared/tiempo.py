"""Manejo de tiempo consistente en toda la aplicación. """

from datetime import datetime
from zoneinfo import ZoneInfo

ZONA_HORARIA_COLOMBIA = ZoneInfo("America/Bogota")


def ahora_utc() -> datetime:
    """Devuelve la fecha y hora actual en Colombia (UTC-5)"""
    return datetime.now(ZONA_HORARIA_COLOMBIA).replace(tzinfo=None)

