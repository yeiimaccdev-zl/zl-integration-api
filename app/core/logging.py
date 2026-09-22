"""Logging estructurado en JSON, con soporte de identificador de solicitud
para correlacionar las líneas de log de una misma petición.
"""
import logging
import os
import sys
from contextvars import ContextVar
from logging.handlers import RotatingFileHandler

identificador_solicitud_ctx: ContextVar[str] = ContextVar("identificador_solicitud", default="-")

_FORMATO_JSON = (
    '{"fecha_hora":"%(asctime)s","nivel":"%(levelname)s",'
    '"identificador_solicitud":"%(identificador_solicitud)s",'
    '"logger":"%(name)s","mensaje":"%(message)s"}'
)

_TAMANO_MAXIMO_ARCHIVO_BYTES = 50 * 1024 * 1024  # 50 MB por archivo
_CANTIDAD_ARCHIVOS_HISTORICOS = 5


class _FiltroIdentificadorSolicitud(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.identificador_solicitud = identificador_solicitud_ctx.get()
        return True


def configurar_logging(entorno: str, directorio_logs: str) -> None:
    """Configura el logger raiz de la aplicacion como salida por consola y archivo rotativo."""
    formato = logging.Formatter(fmt=_FORMATO_JSON)
    filtro = _FiltroIdentificadorSolicitud()

    manejador_consola = logging.StreamHandler(sys.stdout)
    manejador_consola.setFormatter(formato)
    manejador_consola.addFilter(filtro)

    os.makedirs(directorio_logs, exist_ok=True)
    manejador_archivo = RotatingFileHandler(
        filename=os.path.join(directorio_logs, "zl-integration-api.log"),
        maxBytes=_TAMANO_MAXIMO_ARCHIVO_BYTES,
        backupCount=_CANTIDAD_ARCHIVOS_HISTORICOS,
        encoding="utf-8",
    )
    manejador_archivo.setFormatter(formato)
    manejador_archivo.addFilter(filtro)

    logger_raiz = logging.getLogger()
    logger_raiz.handlers = [manejador_consola, manejador_archivo]
    logger_raiz.setLevel(logging.DEBUG if entorno == "desarrollo" else logging.INFO)


def obtener_logger(nombre: str) -> logging.Logger:
    return logging.getLogger(nombre)
