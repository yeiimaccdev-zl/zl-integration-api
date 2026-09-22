"""Rota la llave de API de un sistema consumidor.

Debe ejecutarse cuando el ciclo de vigencia de una llave se cumple, o
cuando el responsable reporta la pérdida de la llave vigente. Genera un
nuevo valor de llave para el mismo registro (mismo sistema y responsable)
y reinicia sus contadores de uso.

Uso:
    python scripts/rotar_llave.py <sistema>
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.database import SessionLocal  # noqa: E402
from app.modules.seguridad.models import LlaveApiModel  # noqa: E402
from app.modules.seguridad.servicio import rotar_llave  # noqa: E402


def rotar_llave_de_sistema(sistema: str) -> None:
    db = SessionLocal()
    try:
        llave = db.query(LlaveApiModel).filter(LlaveApiModel.sistema == sistema).first()
        if llave is None:
            print(f"No existe una llave registrada para el sistema '{sistema}'.")
            return

        resultado = rotar_llave(db, llave=llave)
        print(
            f"Llave rotada para sistema={resultado.sistema} "
            f"responsable={resultado.nombre_usuario_responsable} "
            f"nueva_expiracion={resultado.fecha_expiracion:%Y-%m-%d}"
        )
        print(f"API_KEY={resultado.clave_api}")
    finally:
        db.close()


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Uso: python scripts/rotar_llave.py <sistema>")
        sys.exit(1)
    rotar_llave_de_sistema(sys.argv[1])
