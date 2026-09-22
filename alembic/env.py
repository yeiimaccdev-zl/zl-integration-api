"""Configuración de Alembic para zl-integration-api.

Reutiliza la configuración de app.core.config . 
Las migraciones gestionan únicamente el esquema de la
base MySQL, la base de Prosoft es una fuente externa de solo
lectura.
"""
from logging.config import fileConfig

from alembic import context
from app.core.config import get_settings
from app.core.database import Base, mysql_engine  # Se importa mysql_engine directamente

# Se importan todos los modelos para que Alembic los detecte al generar
# una migración automáticamente alembic revision --autogenerate.
from app.modules.auditoria import models as _modelos_auditoria  # noqa: F401
from app.modules.seguridad import models as _modelos_seguridad  # noqa: F401

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

settings = get_settings()

# Se adapta % duplicándolo como %%, evitando el error de interpolación en configparser
config.set_main_option("sqlalchemy.url", settings.MYSQL_DATABASE_URL.replace("%", "%%"))

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """Ejecuta migraciones en modo 'offline' (genera scripts SQL sin conectarse)."""
    context.configure(
        url=settings.MYSQL_DATABASE_URL,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Ejecuta migraciones en modo 'online' (aplicando cambios directamente en la BD)."""
    with mysql_engine.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()