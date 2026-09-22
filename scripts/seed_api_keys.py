"""Genera las llaves de API iniciales para los sistemas consumidores.

Cada llave se muestra en texto plano una única vez, en la salida de este
script. Debe guardarse de inmediato en el gestor de credenciales del
equipo; no queda almacenada en ningún otro lugar y no puede recuperarse
después.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.database import Base, SessionLocal, mysql_engine  # noqa: E402
from app.modules.seguridad.servicio import crear_llave  # noqa: E402

# sistema, responsable, alcance(s). Varios alcances se combinan separados por coma.
LLAVES_A_CREAR = [
    ("power_bi", "Equipo de Inteligencia de Negocio", "colaboradores:basico"),
    ("zlhub", "Equipo ZLHub", "colaboradores:basico"),
    ("sga", "Equipo de Desarrollo SGA", "colaboradores:basico,colaboradores:costos"),
]


def sembrar_llaves_api() -> None:
    Base.metadata.create_all(bind=mysql_engine)
    db = SessionLocal()
    try:
        for sistema, responsable, alcance in LLAVES_A_CREAR:
            resultado = crear_llave(
                db, sistema=sistema, nombre_usuario_responsable=responsable, alcance=alcance
            )
            print(
                f"sistema={resultado.sistema:10s} "
                f"responsable={resultado.nombre_usuario_responsable:30s} "
                f"expira={resultado.fecha_expiracion:%Y-%m-%d} "
                f"API_KEY={resultado.clave_api}"
            )
    finally:
        db.close()


if __name__ == "__main__":
    sembrar_llaves_api()
