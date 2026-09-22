""" Punto de integracion entre FastAPI y el servicio de seguridad.

Este modulo solo conoce detalles de FastAPI como encabezados, dependencias,
toda la logica de negocio de validacion vive en
app.modules.seguridad.servicio, sin depender de FastAPI.

El prefijo de la llave recibida se registra de forma
incondicional, antes de cualquier validación. Así incluso una solicitud
que falla por completo con llave inexistente, formato invalido, o un intento
de exploracion tercera, deja un rastro identificable en auditoría sin que el
secreto completo quede expuesto.
"""
from fastapi import Depends, Request, Security
from fastapi.security import APIKeyHeader
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.modules.seguridad.servicio import InformacionAutenticacion, validar_llave
from app.shared.constantes import LONGITUD_MAXIMA_PREFIJO_LLAVE_AUDITADO
from app.shared.excepciones import LlaveApiInvalidaError
from app.shared.saneamiento import enmascarar_llave_intentada

encabezado_llave_api = APIKeyHeader(name="X-API-Key", auto_error=False)


def requerir_alcance_minimo(alcance_requerido: str):
    """Crea una dependencia de FastAPI que exige una API Key activa con, como
    mínimo, el alcance indicado.

    "Como mínimo" porque los alcances son jerárquicos (ver
    `JERARQUIA_ALCANCES` en `app.shared.constantes`): una llave con un
    alcance superior también satisface la exigencia de uno inferior que
    esté contenido en él. Por ejemplo, `requerir_alcance_minimo(ALCANCE_COLABORADORES_BASICO)`
    deja pasar tanto a una llave con `colaboradores:basico` como a una con
    `colaboradores:costos` — costos incluye básico, no es un permiso
    paralelo. La expansión ocurre en `validar_llave`
    (`app.modules.seguridad.servicio`), no aquí; esta función solo compara
    el resultado ya expandido contra `alcance_requerido`.

    Esto es intencional y es lo que permite que un mismo endpoint (ver
    `app.integraciones.prosoft.router`) devuelva más o menos detalle según
    el alcance real de la llave, en vez de necesitar una ruta separada por
    cada nivel de detalle. Quien solo quiera aceptar el alcance exacto,
    sin honrar la jerarquía, debe resolverlo en el propio endpoint
    comparando contra `info_autenticacion.alcances`.
    """

    def dependencia(
        request: Request,
        api_key: str | None = Security(encabezado_llave_api),
        db: Session = Depends(get_db),
    ) -> InformacionAutenticacion:
        request.state.prefijo_llave_intentada = enmascarar_llave_intentada(
            api_key, LONGITUD_MAXIMA_PREFIJO_LLAVE_AUDITADO
        )

        if not api_key:
            raise LlaveApiInvalidaError("Se requiere una API Key en el encabezado 'X-API-Key'")

        info_autenticacion = validar_llave(db, clave_plana=api_key, alcance_requerido=alcance_requerido)

        request.state.sistema_consumidor = info_autenticacion.sistema
        request.state.identificador_llave_api = info_autenticacion.identificador_llave
        request.state.responsable_llave_api = info_autenticacion.responsable

        return info_autenticacion

    return dependencia
