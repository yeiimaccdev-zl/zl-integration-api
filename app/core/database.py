"""Conexiones a las bases de datos que utiliza el sistema

MySQL con base con tablas de llaves de API y auditoría.
SQL Server con acceso a solo lectura de los datos.

Cada motor mantiene su propio pool de conexiones de forma independiente y
ambos tienen un tiempo maximo de espera configurado explícitamente.
"""
from collections.abc import Generator
from contextlib import contextmanager

from sqlalchemy import create_engine, text
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.core.config import get_settings

settings = get_settings()


class Base(DeclarativeBase):
    """Base declarativa para los modelos propios de la aplicación con MySQL."""


# Base de datos MySQL
mysql_engine = create_engine(
    settings.MYSQL_DATABASE_URL,
    pool_pre_ping=True,
    connect_args={"connect_timeout": settings.MYSQL_TIMEOUT_SEGUNDOS},
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=mysql_engine)


def get_db() -> Generator[Session, None, None]:
    """Dependencia de FastAPI entrega una sesión sobre la base propia de la aplicación."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# Base datos fuente de solo lectura SQL Server - Prosoft
prosoft_engine = create_engine(
    settings.PROSOFT_DATABASE_URL,
    pool_pre_ping=True,
    connect_args={
        "timeout": settings.PROSOFT_TIMEOUT_SEGUNDOS,
        "login_timeout": settings.PROSOFT_TIMEOUT_SEGUNDOS,
    },
)


@contextmanager
def get_prosoft_connection():
    """Entrega una conexion de solo lectura hacia Prosoft."""
    conn = prosoft_engine.connect()
    try:
        yield conn
    finally:
        conn.close()


def verificar_conexion_mysql() -> bool:
    """Confirma que la base propia responde, ejecutando una consulta basica.

    Se usa en el endpoint de salud
    """
    try:
        with mysql_engine.connect() as conexion:
            conexion.execute(text("SELECT 1"))
        return True
    except Exception:
        return False


def verificar_conexion_prosoft() -> bool:
    """Confirma que Prosoft responde a través de la VPN, ejecutando una consulta basica."""
    try:
        with prosoft_engine.connect() as conexion:
            conexion.execute(text("SELECT 1"))
        return True
    except Exception:
        return False
