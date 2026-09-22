"""Configuración de la aplicación, cargada desde variables de entorno.

Las cadenas de conexión son obligatorias y no tienen valor por defecto: la
aplicación debe fallar al iniciar si el entorno no está correctamente
configurado, en lugar de arrancar silenciosamente contra un destino incorrecto.
"""
from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict

from app.core.cors import PoliticaCorsModulo
from app.shared.constantes import DIAS_EXPIRACION_MAXIMO_LLAVE_API


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    PROJECT_NAME: str = "zl-integration-api"

    # "desarrollo" habilita comportamientos convenientes para el equipo creación
    # automática de tablas, documentación interactiva siempre visible. Ninguno
    # de esos comportamientos estara activo en "produccion".
    ENTORNO: Literal["desarrollo", "produccion"] = "desarrollo"

    # Base de datos MySQL llaves de acceso y auditoría.
    MYSQL_DATABASE_URL: str
    MYSQL_TIMEOUT_SEGUNDOS: int = 30

    # Fuente externa de solo lectura SQL Server - Prosoft.
    PROSOFT_DATABASE_URL: str
    PROSOFT_TIMEOUT_SEGUNDOS: int = 30

    # Vigencia maxima permitida para una llave de API, en días.
    LLAVE_API_DIAS_EXPIRACION_MAXIMO: int = DIAS_EXPIRACION_MAXIMO_LLAVE_API

    # Directorio donde se escriben los archivos de log de la aplicación
    DIRECTORIO_LOGS: str = "logs"

    # Políticas de CORS por prefijo de ruta, ej.:
    #   {"/api/v1/integraciones/colaboradores": {"origenes": ["https://sga.zonalogistica.com.co"]}}
    # Vacío por defecto: ningún origen de navegador puede leer las
    # respuestas hasta que se declare explícitamente aquí. Ver
    # app/core/cors.py para el detalle de cada campo y por qué no se
    # admite "*" como origen.
    CORS_POLITICAS: dict[str, PoliticaCorsModulo] = {}

    @property
    def es_produccion(self) -> bool:
        return self.ENTORNO == "produccion"


@lru_cache
def get_settings() -> Settings:
    """Devuelve la configuración cacheada de la aplicación."""
    return Settings()
