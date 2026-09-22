"""Consulta de colaboradores contra Prosoft.

Las variables como cedula, nombre, estado_bit.
"""
from sqlalchemy import text

from app.core.database import get_prosoft_connection
from app.shared.excepciones import FuenteExternaNoDisponibleError, ParametroInvalidoError

CONSULTA_COLABORADORES = text(
    """
    SELECT
          ter.num_docu AS cedula
        , ter.nombre AS nombre_completo
        , ISNULL(STRING_AGG(TRIM(cor.correo), ' | '), '') AS correos
        , ISNULL(cargo.nombre, '') AS cargo
        , ISNULL(STRING_AGG(TRIM(tel.fijo), ' | '), '') AS telefono
        , ISNULL(STRING_AGG(TRIM(tel.celular), ' | '), '') AS celular
        , ISNULL(CONVERT(VARCHAR(10), emp.fecha_ingreso, 23), '') AS fecha_ingreso
        , ISNULL(CONVERT(VARCHAR(10), emp.fecha_retiro, 23), '') AS fecha_retiro
        , CASE
              WHEN ter.estado = 1 THEN 'Activo'
              ELSE 'Inactivo'
          END AS estado
        , ISNULL(centro_costo.descripcion, '') AS gerencia
        , ISNULL(sucursal.nombre, '') AS sede
        , ISNULL(centro_trabajo.nombre, '') AS division
        , ISNULL(area.nombre, '') AS area_departamento
        , ISNULL(CONVERT(VARCHAR(20), emp.sueldo), '') AS salario
        , ISNULL(CONVERT(VARCHAR(20), emp.aux_transporte), '') AS auxilio_transporte
    FROM Tercero AS ter
    LEFT JOIN Empleados AS emp ON ter.id_tercero = emp.tercero_id
    LEFT JOIN Correos AS cor ON ter.id_tercero = cor.tercero_id
    LEFT JOIN PerfilesCargo AS cargo ON emp.cargo_id = cargo.codigo
    LEFT JOIN Telefonos AS tel ON ter.id_tercero = tel.tercero_id
    LEFT JOIN CentroCosto AS centro_costo ON emp.cencosto_id = centro_costo.codigo
    LEFT JOIN Sucursales AS sucursal ON emp.sucursalid = sucursal.id
    LEFT JOIN Centro_Trabajo AS centro_trabajo ON emp.centrotrabajo_id = centro_trabajo.id
    LEFT JOIN Areas AS area ON emp.AreaId = area.id
    WHERE
                (:cedula IS NULL OR ter.num_docu = :cedula)
    AND (:nombre IS NULL OR ter.nombre LIKE :nombre)
    AND (:estado_bit IS NULL OR ter.estado = :estado_bit)
    GROUP BY
          ter.num_docu
        , ter.nombre
        , cargo.nombre
        , emp.fecha_ingreso
        , emp.fecha_retiro
        , ter.estado
        , centro_costo.descripcion
        , sucursal.nombre
        , centro_trabajo.nombre
        , area.nombre
        , emp.sueldo
        , emp.aux_transporte
    ORDER BY
          ter.nombre
        , emp.fecha_ingreso DESC
    """
)

_ESTADOS_VALIDOS = {"ACTIVO": 1, "INACTIVO": 0}


def traducir_estado(estado: str | None) -> int | None:
    """Traduce el filtro de estado ("ACTIVO"/"INACTIVO") al valor interno de Prosoft.

    Se aísla como función pura, sin acceso a base de datos, para poder
    probarla de forma directa.
    """
    if estado is None:
        return None

    estado_normalizado = estado.strip().upper()
    if estado_normalizado not in _ESTADOS_VALIDOS:
        raise ParametroInvalidoError("El parámetro 'estado' debe ser ACTIVO o INACTIVO")

    return _ESTADOS_VALIDOS[estado_normalizado]


def consultar_colaboradores(
    cedula: str | None = None, nombre: str | None = None, estado: str | None = None
) -> list[dict]:
    """Consulta colaboradores en Prosoft con filtros opcionales.

    cedula: coincidencia exacta por número de documento.
    nombre: coincidencia parcial que contiene el texto indicado.
    estado: "ACTIVO" o "INACTIVO".
    """
    nombre_como = f"%{nombre.strip()}%" if nombre else None
    estado_bit = traducir_estado(estado)

    try:
        with get_prosoft_connection() as conexion:
            resultado = conexion.execute(
                CONSULTA_COLABORADORES, {"cedula": cedula, "nombre": nombre_como, "estado_bit": estado_bit}
            )
            return [dict(fila._mapping) for fila in resultado]
    except ParametroInvalidoError:
        raise
    except Exception as excepcion:
        raise FuenteExternaNoDisponibleError(f"Error de conexión con Prosoft: {excepcion}") from excepcion
