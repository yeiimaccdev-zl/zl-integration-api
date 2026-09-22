""" Endpoints de colaboradores

El nivel de detalle de la respuesta se ajusta automaticamente segun el
alcance de la API Key utilizada: un sistema con alcance de costos recibe
salario y auxilio de transporte tanto en el listado como en el detalle
individual; un sistema con solo el alcance básico recibe únicamente los
datos generales.

Esto es posible porque los alcances son jerárquicos: "colaboradores:costos"
incluye a "colaboradores:basico" (ver JERARQUIA_ALCANCES en
app/shared/constantes.py). Por eso listar_colaboradores y
obtener_colaborador piden ALCANCE_COLABORADORES_BASICO como el *mínimo*
para entrar (ver requerir_alcance_minimo en app/core/security.py) y una
llave con solo "colaboradores:costos" en la base de datos también pasa esa
validación — no hace falta listar ambos alcances por separado al crear la
llave. Qué payload se devuelve (ColaboradorBasico o ColaboradorCostos) es
una decisión aparte, resuelta en mapear_colaborador() a partir de los
alcances ya expandidos de la llave.
"""
from fastapi import APIRouter, Depends, Query, Request

from app.core.security import requerir_alcance_minimo
from app.integraciones.prosoft.client import consultar_colaboradores
from app.integraciones.prosoft.mapper import mapear_colaborador
from app.integraciones.prosoft.schemas import ColaboradorBasico, ColaboradorCostos
from app.modules.seguridad.servicio import InformacionAutenticacion
from app.shared.constantes import ALCANCE_COLABORADORES_BASICO, ALCANCE_COLABORADORES_COSTOS
from app.shared.excepciones import RecursoNoEncontradoError

router = APIRouter(prefix="/colaboradores", tags=["Colaboradores"])


@router.get("", response_model=list[ColaboradorCostos | ColaboradorBasico])
def listar_colaboradores(
    request: Request,
    cedula: str | None = Query(default=None, description="Filtra por número de documento exacto"),
    nombre: str | None = Query(default=None, description="Filtra por coincidencia parcial del nombre"),
    estado: str | None = Query(default=None, description="ACTIVO o INACTIVO"),
    # Mínimo básico: una llave con alcance de costos también entra aquí
    # (costos incluye básico por jerarquía) y recibe el listado con
    # salario/auxilio de transporte incluido, gracias a mapear_colaborador().
    info_autenticacion: InformacionAutenticacion = Depends(requerir_alcance_minimo(ALCANCE_COLABORADORES_BASICO)),
):
    filas = consultar_colaboradores(cedula=cedula, nombre=nombre, estado=estado)
    # Cantidad de registros devueltos necesario en auditoría para
    # detectar descargas masivas.
    request.state.cantidad_registros = len(filas)
    return [mapear_colaborador(fila, info_autenticacion.alcances) for fila in filas]


@router.get("/{cedula}", response_model=ColaboradorCostos | ColaboradorBasico)
def obtener_colaborador(
    request: Request,
    cedula: str,
    # Mismo criterio que listar_colaboradores: mínimo básico, una llave de
    # costos entra igual y recibe el detalle con costos incluido.
    info_autenticacion: InformacionAutenticacion = Depends(requerir_alcance_minimo(ALCANCE_COLABORADORES_BASICO)),
):
    filas = consultar_colaboradores(cedula=cedula)
    request.state.cantidad_registros = len(filas)
    if not filas:
        raise RecursoNoEncontradoError(f"No se encontró un colaborador con cédula {cedula}")
    return mapear_colaborador(filas[0], info_autenticacion.alcances)


@router.get("/{cedula}/costos", response_model=ColaboradorCostos)
def obtener_costos_colaborador(
    request: Request,
    cedula: str,
    # A diferencia de los dos endpoints anteriores, aquí el mínimo exigido
    # es costos: la jerarquía es unidireccional (básico nunca otorga
    # costos), así que una llave con solo alcance básico recibe 403 aquí.
    info_autenticacion: InformacionAutenticacion = Depends(requerir_alcance_minimo(ALCANCE_COLABORADORES_COSTOS)),
):
    """Endpoint dedicado para sistemas que cuentan únicamente con el alcance de costos."""
    filas = consultar_colaboradores(cedula=cedula)
    request.state.cantidad_registros = len(filas)
    if not filas:
        raise RecursoNoEncontradoError(f"No se encontró un colaborador con cédula {cedula}")
    return ColaboradorCostos(**filas[0])
