"""Punto de entrada de zl-integration-api.

Expone la documentación interactiva en /docs (solo en entorno de
desarrollo) y los endpoints de colaboradores, que reemplazan las consultas
que antes se resolvían contra las APIs de Buk.
"""
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.responses import JSONResponse

from app.api_v1 import router as api_v1_router
from app.core.config import get_settings
from app.core.cors import MiddlewareCorsPorModulo
from app.core.database import Base, mysql_engine, verificar_conexion_mysql, verificar_conexion_prosoft
from app.core.exceptions import registrar_manejadores_excepciones
from app.core.logging import configurar_logging, obtener_logger
from app.core.middleware import MiddlewareAuditoria, MiddlewareCabecerasSeguridad
from app.modules.auditoria.models import RegistroAuditoriaModel  # noqa: F401 - registra la tabla
from app.modules.seguridad.models import LlaveApiModel  # noqa: F401 - registra la tabla

settings = get_settings()
configurar_logging(settings.ENTORNO, settings.DIRECTORIO_LOGS)
logger = obtener_logger("zl_integration_api.main")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Prepara el esquema de la base propia solo en desarrollo.

    En producción, el esquema se gestiona exclusivamente con migraciones
    versionadas (`alembic upgrade head`), ejecutadas como parte del
    despliegue, nunca de forma automática al arrancar el proceso.
    """
    if not settings.es_produccion:
        Base.metadata.create_all(bind=mysql_engine)
        logger.info("Entorno de desarrollo: esquema de base de datos verificado con create_all().")
    yield


def _resolver_urls_documentacion(es_produccion: bool) -> tuple[str | None, str | None, str | None]:
    """Determina si la documentación interactiva debe exponerse, según el entorno.

    Aislada como función pura para poder probarla sin reconstruir la
    aplicación completa.
    """
    if es_produccion:
        return None, None, None
    return "/docs", "/redoc", "/openapi.json"


_docs_url, _redoc_url, _openapi_url = _resolver_urls_documentacion(settings.es_produccion)

app = FastAPI(
    title=settings.PROJECT_NAME,
    version="1.0.0",
    description=(
        "API de integraciones de Zona Logística."
    ),
    lifespan=lifespan,
    # La documentación interactiva queda deshabilitada en producción como
    # segunda capa de defensa, independiente de lo que restrinja el proxy
    # reverso (IIS) a nivel de red.
    docs_url=_docs_url,
    redoc_url=_redoc_url,
    openapi_url=_openapi_url,
)

registrar_manejadores_excepciones(app)

# El nombre de servicio identifica, dentro de la tabla de auditoría, qué
# proceso generó cada registro. Debe mantenerse estable en cada despliegue.
# El orden de registro importa: el middleware que se agrega último es el
# que envuelve a los demás. Las cabeceras de seguridad quedan aplicadas
# incluso a las respuestas generadas por el middleware de auditoría, y el
# de CORS queda como el más externo de todos para poder responder una
# solicitud de preflight (OPTIONS) sin que pase por auditoría ni por
# ninguna dependencia de autenticación.
app.add_middleware(MiddlewareAuditoria, servicio=settings.PROJECT_NAME)
app.add_middleware(MiddlewareCabecerasSeguridad)
app.add_middleware(MiddlewareCorsPorModulo, politicas=settings.CORS_POLITICAS)

app.include_router(api_v1_router)


@app.get("/health", tags=["Sistema"])
def health_check():
    """Verifica que el servicio y sus dependencias reales estén disponibles.

    Un proceso vivo no es lo mismo que un servicio disponible: este
    endpoint confirma también que la base propia y Prosoft respondan, para
    que una herramienta de monitoreo pueda distinguir ambos casos.
    """
    mysql_disponible = verificar_conexion_mysql()
    prosoft_disponible = verificar_conexion_prosoft()
    saludable = mysql_disponible and prosoft_disponible

    return JSONResponse(
        status_code=200 if saludable else 503,
        content={
            "status": "ok" if saludable else "degradado",
            "mysql": "arriba" if mysql_disponible else "no_disponible",
            "prosoft": "arriba" if prosoft_disponible else "no_disponible",
        },
    )
