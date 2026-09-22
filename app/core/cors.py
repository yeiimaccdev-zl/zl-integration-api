"""CORS con una política distinta por prefijo de ruta.

`starlette.middleware.cors.CORSMiddleware` (el que trae FastAPI) solo admite
una única política global para toda la aplicación. Este proyecto necesita
orígenes distintos según el módulo (ej. `integraciones/colaboradores` puede
autorizar un origen y `sga/transporte` otro, distinto), así que se
implementa aquí el mecanismo de CORS a mano, aplicando la política del
prefijo de ruta más específico que coincida con cada solicitud.

Conceptos clave para quien mantenga esto:
- CORS es una restricción que aplica el **navegador**, no el servidor.
  Una solicitud sin encabezado `Origin` (Power BI, otro backend, curl,
  Postman, una automatización) no es una solicitud CORS: se deja pasar sin
  tocarla, este middleware no reemplaza la autenticación por API Key.
- Una ruta sin política configurada no recibe ningún encabezado CORS. Un
  navegador bloqueará la lectura de la respuesta desde JavaScript aunque el
  servidor haya respondido 200 — es el comportamiento por defecto que se
  quiere (denegar salvo declaración explícita), igual que el resto de la
  configuración del proyecto (ver `core/config.py`).
- No se admite `"*"` como origen: estos endpoints pueden exponer datos
  operativos de colaboradores, así que cada origen autorizado debe quedar
  declarado de forma explícita en `CORS_POLITICAS`.
- Enviar una API Key (`X-API-Key`) desde JavaScript de navegador implica que
  ese valor queda visible en el código fuente/consola de red del cliente:
  CORS controla qué origen puede *leer* la respuesta, no protege el secreto
  en sí. Para un módulo pensado para ser llamado directo desde el
  navegador, evaluar si el dato expuesto amerita ese riesgo o si conviene
  que el frontend hable con su propio backend, y que sea ese backend quien
  llame a `zl-integration-api` con la API Key real.
"""
from pydantic import BaseModel, Field, field_validator
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import PlainTextResponse, Response
from starlette.types import ASGIApp


class PoliticaCorsModulo(BaseModel):
    """Política de CORS aplicada a un prefijo de ruta.

    origenes: orígenes exactos permitidos (esquema + host + puerto, sin
        barra final), ej. "https://sga.zonalogistica.com.co". No se admite
        "*".
    metodos: métodos HTTP permitidos en la solicitud real.
    encabezados: encabezados que el navegador puede enviar en la solicitud
        real, además de los que ya permite el propio navegador. Si el
        módulo requiere `X-API-Key` desde el navegador, debe listarse aquí
        explícitamente o el preflight lo rechazará.
    credenciales: si se deben aceptar cookies/credenciales de navegador.
        Debe quedar en False salvo que el módulo use autenticación por
        cookie en vez de X-API-Key.
    """

    origenes: list[str] = Field(min_length=1)
    metodos: list[str] = ["GET"]
    encabezados: list[str] = ["Content-Type", "X-API-Key"]
    credenciales: bool = False

    @field_validator("origenes")
    @classmethod
    def _rechazar_comodin(cls, valor: list[str]) -> list[str]:
        if "*" in valor:
            raise ValueError(
                "CORS_POLITICAS no admite '*' como origen: cada origen autorizado "
                "debe declararse explícitamente."
            )
        return valor


class MiddlewareCorsPorModulo(BaseHTTPMiddleware):
    """Aplica CORS usando la política del prefijo de ruta más específico.

    Uso en el punto de entrada de la aplicación:
    app.add_middleware(MiddlewareCorsPorModulo, politicas=settings.CORS_POLITICAS)

    Debe agregarse como el último middleware (el más externo — ver el
    comentario sobre orden de middlewares en `main.py`), para poder
    responder una solicitud de preflight antes de que llegue a cualquier
    otro middleware o dependencia de autenticación.
    """

    def __init__(self, app: ASGIApp, politicas: dict[str, PoliticaCorsModulo]) -> None:
        super().__init__(app)
        # El prefijo más largo (más específico) se evalúa primero, para que
        # una política de "/sga/transporte" gane sobre una de "/sga" cuando
        # ambas coincidan con la misma ruta.
        self._politicas: list[tuple[str, PoliticaCorsModulo]] = sorted(
            ((prefijo.rstrip("/") or "/", politica) for prefijo, politica in politicas.items()),
            key=lambda item: len(item[0]),
            reverse=True,
        )

    def _resolver_politica(self, ruta: str) -> PoliticaCorsModulo | None:
        for prefijo, politica in self._politicas:
            if ruta == prefijo or ruta.startswith(f"{prefijo}/"):
                return politica
        return None

    @staticmethod
    def _origen_permitido(origen: str, politica: PoliticaCorsModulo) -> bool:
        return origen in politica.origenes

    async def dispatch(self, request: Request, call_next):
        origen = request.headers.get("origin")

        # Sin encabezado Origin no es una solicitud CORS: es una llamada
        # servidor-a-servidor (Power BI, otro backend, una automatización,
        # curl/Postman). No hay nada de CORS que validar ni agregar.
        if origen is None:
            return await call_next(request)

        politica = self._resolver_politica(request.url.path)
        if politica is None:
            # Ruta sin política declarada: se deja pasar la solicitud (el
            # servidor igual la procesa, la autenticación por API Key sigue
            # aplicando), pero sin encabezados CORS el navegador bloqueará
            # que el JavaScript de origen cruzado lea la respuesta.
            return await call_next(request)

        es_preflight = request.method == "OPTIONS" and "access-control-request-method" in request.headers
        if es_preflight:
            return self._responder_preflight(request, origen, politica)

        response = await call_next(request)
        self._agregar_encabezados_cors(response, origen, politica)
        return response

    def _agregar_encabezados_cors(self, response: Response, origen: str, politica: PoliticaCorsModulo) -> None:
        if not self._origen_permitido(origen, politica):
            return
        response.headers["Access-Control-Allow-Origin"] = origen
        response.headers["Vary"] = "Origin"
        if politica.credenciales:
            response.headers["Access-Control-Allow-Credentials"] = "true"

    def _responder_preflight(self, request: Request, origen: str, politica: PoliticaCorsModulo) -> Response:
        if not self._origen_permitido(origen, politica):
            return PlainTextResponse("Origen no permitido por la política CORS de esta ruta.", status_code=400)

        metodo_solicitado = request.headers.get("access-control-request-method", "").upper()
        metodos_permitidos = {metodo.upper() for metodo in politica.metodos}
        if metodo_solicitado and metodo_solicitado not in metodos_permitidos:
            return PlainTextResponse(f"Método '{metodo_solicitado}' no permitido en esta ruta.", status_code=400)

        encabezados_solicitados = request.headers.get("access-control-request-headers", "")
        encabezados_permitidos = {encabezado.lower() for encabezado in politica.encabezados}
        for encabezado in (valor.strip() for valor in encabezados_solicitados.split(",") if valor.strip()):
            if encabezado.lower() not in encabezados_permitidos:
                return PlainTextResponse(f"Encabezado '{encabezado}' no permitido en esta ruta.", status_code=400)

        respuesta = PlainTextResponse("OK", status_code=200)
        respuesta.headers["Access-Control-Allow-Origin"] = origen
        respuesta.headers["Access-Control-Allow-Methods"] = ", ".join(politica.metodos)
        respuesta.headers["Access-Control-Allow-Headers"] = ", ".join(politica.encabezados)
        respuesta.headers["Vary"] = "Origin"
        # Cuánto puede el navegador cachear el resultado de este preflight
        # antes de repetirlo. 600s (10 min) es un punto intermedio razonable.
        respuesta.headers["Access-Control-Max-Age"] = "600"
        if politica.credenciales:
            respuesta.headers["Access-Control-Allow-Credentials"] = "true"
        return respuesta
