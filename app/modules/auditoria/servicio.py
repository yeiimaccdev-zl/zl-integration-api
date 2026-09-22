"""Servicio de auditoria.

Expone una unica funcion de escritura, que es el unico punto del sistema autorizado a insertar filas en la tabla de
auditoría. No existen funciones de actualización ni de borrado, el historial una vez escrito, debe ser inmutable.
"""
import logging
from datetime import datetime

from sqlalchemy.orm import Session

from app.modules.auditoria.models import RegistroAuditoriaModel
from app.shared.tiempo import ahora_utc

logger = logging.getLogger("zl_integration_api.auditoria")


def registrar_solicitud(
    db: Session,
    *,
    identificador_solicitud: str,
    servicio: str,
    metodo_http: str,
    ruta: str,
    parametros_consulta: str | None,
    sistema_consumidor: str | None,
    identificador_llave_api: int | None,
    responsable_llave_api: str | None,
    prefijo_llave_intentada: str | None,
    ip_origen: str | None,
    ip_real_cliente: str | None,
    agente_usuario: str | None,
    codigo_respuesta: int,
    duracion_ms: float,
    tamano_respuesta_bytes: int | None,
    cantidad_registros: int | None,
    categoria_error: str | None,
    mensaje_error: str | None,
    fecha_hora_inicio: datetime,
) -> None:
    """Inserta un registro de auditoria.

    Un fallo al escribir la auditoria nunca debe interrumpir la respuesta
    real al consumidor, cualquier error se registra en el log de la
    aplicación y se contiene aquí.
    """
    try:
        registro = RegistroAuditoriaModel(
            identificador_solicitud=identificador_solicitud,
            servicio=servicio,
            metodo_http=metodo_http,
            ruta=ruta,
            parametros_consulta=parametros_consulta,
            sistema_consumidor=sistema_consumidor,
            identificador_llave_api=identificador_llave_api,
            responsable_llave_api=responsable_llave_api,
            prefijo_llave_intentada=prefijo_llave_intentada,
            ip_origen=ip_origen,
            ip_real_cliente=ip_real_cliente,
            agente_usuario=agente_usuario,
            codigo_respuesta=codigo_respuesta,
            exitosa=codigo_respuesta < 400,
            categoria_error=categoria_error,
            mensaje_error=mensaje_error,
            tamano_respuesta_bytes=tamano_respuesta_bytes,
            cantidad_registros=cantidad_registros,
            duracion_ms=duracion_ms,
            fecha_hora_inicio=fecha_hora_inicio,
            fecha_hora_fin=ahora_utc(),
        )
        db.add(registro)
        db.commit()
    except Exception:
        logger.exception("No fue posible guardar el registro de auditoría")
