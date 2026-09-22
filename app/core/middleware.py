""" Middleware que asigna un identificador de correlación a cada solicitud y
delega su registro en el servicio de auditoría app.modules.auditoria.

Se aplica a nivel de aplicacion por lo que cubre todos los
endpoints expuestos, sin necesidad de instrumentar cada uno por separado.
Toda la información recogida aquí proviene de dos fuentes: 
los encabezados propios de la solicitud HTTP. 
request.state donde las capas de seguridad y de negocio dejan datos de 
auditoría (identidad del sistema consumidor, cantidad de registros devueltos, mensaje y
categoría de error).
"""
import time
import uuid

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.types import ASGIApp

from app.core.database import SessionLocal
from app.core.logging import identificador_solicitud_ctx
from app.modules.auditoria.servicio import registrar_solicitud
from app.shared.constantes import (
    CATEGORIA_ERROR_INTERNO,
    LONGITUD_MAXIMA_AGENTE_USUARIO_AUDITADO,
    LONGITUD_MAXIMA_PARAMETROS_CONSULTA_AUDITADOS,
)
from app.shared.saneamiento import sanear_texto_auditoria
from app.shared.tiempo import ahora_utc


class MiddlewareAuditoria(BaseHTTPMiddleware):
    """Audita cada solicitud atendida por el servicio.

    Uso en el punto de entrada de la aplicacion:
    app.add_middleware(MiddlewareAuditoria, servicio="zl-integration-api")

    El parámetro servicio identifica, dentro de la tabla de auditoría, que proceso genero cada registro.
    """

    def __init__(self, app: ASGIApp, servicio: str) -> None:
        super().__init__(app)
        self.servicio = servicio

    async def dispatch(self, request: Request, call_next):
        identificador_solicitud = str(uuid.uuid4())
        request.state.identificador_solicitud = identificador_solicitud
        token_contexto = identificador_solicitud_ctx.set(identificador_solicitud)

        fecha_hora_inicio = ahora_utc()
        inicio = time.perf_counter()
        try:
            response = await call_next(request)
        except Exception as excepcion:
            # Una excepcion no controlada ninguno de los manejadores
            # de dominio. Igual debe quedar auditada antes de propagarse.
            request.state.mensaje_error = str(excepcion)
            request.state.categoria_error = CATEGORIA_ERROR_INTERNO
            self._registrar(
                request=request,
                identificador_solicitud=identificador_solicitud,
                codigo_respuesta=500,
                duracion_ms=round((time.perf_counter() - inicio) * 1000, 2),
                tamano_respuesta_bytes=None,
                fecha_hora_inicio=fecha_hora_inicio,
            )
            raise
        finally:
            identificador_solicitud_ctx.reset(token_contexto)

        duracion_ms = round((time.perf_counter() - inicio) * 1000, 2)
        response.headers["X-Request-Id"] = identificador_solicitud

        tamano_respuesta_bytes = None
        content_length = response.headers.get("content-length")
        if content_length is not None and content_length.isdigit():
            tamano_respuesta_bytes = int(content_length)

        self._registrar(
            request=request,
            identificador_solicitud=identificador_solicitud,
            codigo_respuesta=response.status_code,
            duracion_ms=duracion_ms,
            tamano_respuesta_bytes=tamano_respuesta_bytes,
            fecha_hora_inicio=fecha_hora_inicio,
        )
        return response

    @staticmethod
    def _resolver_ip_origen_y_real(request: Request) -> tuple[str | None, str | None]:
        """Resuelve la IP de conexión directa y la IP real del cliente.

        ip_origen prioriza la primera IP del encabezado `X-Forwarded-For` es 
        la que el proxy reverso debe reporta como cliente original y solo cae
        de vuelta a la IP de conexión TCP directa cuando ese encabezado no
        existe. 
        ip_real_cliente conserva el valor completo del encabezado
        es la cadena de proxies, si hubo más de uno.

        """
        ip_conexion_directa = request.client.host if request.client else None
        encabezado_xff = request.headers.get("x-forwarded-for")

        """
        NOTAAAAAAA: 
            `X-Forwarded-For` es un encabezado que
            puede enviar el propio cliente y, por lo tanto, es falsificable a
            menos que el proxy reverso (IIS) esté configurado para
            sobrescribirlo — no para anexarlo — en cada solicitud entrante. Si
            esa configuración no está garantizada, este valor debe tratarse
            como orientativo, no como prueba definitiva de origen.
        """

        if not encabezado_xff:
            return ip_conexion_directa, None

        primera_ip = encabezado_xff.split(",")[0].strip() or None
        ip_origen = primera_ip or ip_conexion_directa
        return ip_origen, encabezado_xff

    def _registrar(
        self,
        request: Request,
        identificador_solicitud: str,
        codigo_respuesta: int,
        duracion_ms: float,
        tamano_respuesta_bytes: int | None,
        fecha_hora_inicio,
    ) -> None:
        ip_origen, ip_real_cliente = self._resolver_ip_origen_y_real(request)

        db = SessionLocal()
        try:
            registrar_solicitud(
                db,
                identificador_solicitud=identificador_solicitud,
                servicio=self.servicio,
                metodo_http=request.method,
                ruta=request.url.path,
                parametros_consulta=sanear_texto_auditoria(
                    str(request.query_params) or None, LONGITUD_MAXIMA_PARAMETROS_CONSULTA_AUDITADOS
                ),
                sistema_consumidor=getattr(request.state, "sistema_consumidor", None),
                identificador_llave_api=getattr(request.state, "identificador_llave_api", None),
                responsable_llave_api=getattr(request.state, "responsable_llave_api", None),
                prefijo_llave_intentada=getattr(request.state, "prefijo_llave_intentada", None),
                ip_origen=ip_origen,
                ip_real_cliente=ip_real_cliente,
                agente_usuario=sanear_texto_auditoria(
                    request.headers.get("user-agent"), LONGITUD_MAXIMA_AGENTE_USUARIO_AUDITADO
                ),
                codigo_respuesta=codigo_respuesta,
                duracion_ms=duracion_ms,
                tamano_respuesta_bytes=tamano_respuesta_bytes,
                cantidad_registros=getattr(request.state, "cantidad_registros", None),
                categoria_error=getattr(request.state, "categoria_error", None),
                mensaje_error=getattr(request.state, "mensaje_error", None),
                fecha_hora_inicio=fecha_hora_inicio,
            )
        finally:
            db.close()


class MiddlewareCabecerasSeguridad(BaseHTTPMiddleware):
    """Agrega cabeceras HTTP de seguridad a toda respuesta.

    El proxy reverso (IIS) también debería aplicar varias de estas reglas,
    pero la aplicación no debe depender únicamente de esa configuración
    externa: si el proxy se reconfigura o alguien accede directo al
    proceso, estas cabeceras siguen presentes.
    """

    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        return response
