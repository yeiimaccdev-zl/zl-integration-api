"""Configuración compartida de las pruebas.

Todas las pruebas que requieren base de datos utilizan una base SQLite en
memoria, aislada por prueba, en lugar de conectarse a MySQL o a Prosoft.

El middleware de auditoría abre su propia sesión de base de datos de forma
independiente a la que usan los endpoints (por diseño: no depende de las
dependencias de FastAPI). Para que las pruebas de integración puedan
verificar qué quedó auditado, la fixture `db_session` apunta también la
fábrica de sesiones del middleware al mismo motor en memoria.
"""
import os

os.environ.setdefault("MYSQL_DATABASE_URL", "mysql+pymysql://usuario:clave@localhost:3306/prueba")
os.environ.setdefault("PROSOFT_DATABASE_URL", "mssql+pymssql://usuario:clave@localhost:1433/prueba")

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import app.core.middleware as middleware_modulo
from app.core.database import Base


@pytest.fixture()
def db_session(monkeypatch):
    """Sesión de base de datos en memoria, con el esquema ya creado, aislada por prueba.

    También redirige el middleware de auditoría hacia el mismo motor, para
    que las pruebas de integración puedan verificar los registros que
    efectivamente se guardaron.
    """
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(bind=engine)
    fabrica_sesiones = sessionmaker(bind=engine)

    monkeypatch.setattr(middleware_modulo, "SessionLocal", fabrica_sesiones)

    session = fabrica_sesiones()
    try:
        yield session
    finally:
        session.close()
