"""Servicio de gestion de llaves de API.

Concentra toda la logica de negocio sobre el ciclo de vida de una llave,
creación con vigencia acotada, validación de alcance y expiración, registro
de uso con los contadores diarios y totales, y rotación cuando el ciclo
se cumple o el responsable reporta la pérdida de la llave.

Cuando la validación falla porque la llave
está revocada, expiró, o no tiene el alcance requerido, la excepción
lanzada lleva la identidad del sistema al que pertenecía esa llave. 
Un intento fallido con una llave real es un evento de seguridad.
"""
import hashlib
import secrets
from dataclasses import dataclass
from datetime import date, timedelta

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.modules.seguridad.models import LlaveApiModel
from app.modules.seguridad.schemas import LlaveApiCreada
from app.shared.constantes import JERARQUIA_ALCANCES, PREFIJO_LLAVE_GENERICO, PREFIJOS_LLAVE_POR_SISTEMA
from app.shared.excepciones import AlcanceInsuficienteError, LlaveApiExpiradaError, LlaveApiInvalidaError
from app.shared.tiempo import ahora_utc

settings = get_settings()


@dataclass(frozen=True)
class InformacionAutenticacion:
    """Identidad resuelta a partir de una API Key válida, lista para auditoría."""

    identificador_llave: int
    sistema: str
    responsable: str
    alcances: list[str]

    def tiene_alcance(self, alcance: str) -> bool:
        return alcance in self.alcances


def _generar_par_de_llave(sistema: str) -> tuple[str, str]:
    """Genera una llave en texto plano y su hash.

    La llave incluye un prefijo asociado al sistema consumidor como
    zl-sga_, zl-bi_, útil para identificar visualmente el origen de una
    llave en herramientas de gestión o en un intento fallido registrado en
    auditoría. El prefijo es solo un identificador legible, la validación
    real siempre ocurre contra el hash almacenado, nunca contra el prefijo.
    """
    prefijo = PREFIJOS_LLAVE_POR_SISTEMA.get(sistema, PREFIJO_LLAVE_GENERICO)
    clave_plana = f"{prefijo}_{secrets.token_urlsafe(30)}"
    return clave_plana, _hashear(clave_plana)


def _hashear(clave_plana: str) -> str:
    return hashlib.sha256(clave_plana.encode("utf-8")).hexdigest()


def _expandir_alcances(alcances_asignados: list[str]) -> list[str]:
    """Expande los alcances de una llave según la jerarquía de permisos.

    Un alcance superior (por ejemplo, costos) incluye implícitamente los
    alcances que contiene (por ejemplo, básico), sin que sea necesario
    listarlos por separado al crear la llave. El resultado siempre incluye
    al menos los alcances asignados originalmente.
    """
    efectivos: set[str] = set(alcances_asignados)
    for alcance in alcances_asignados:
        efectivos |= JERARQUIA_ALCANCES.get(alcance, frozenset())
    return sorted(efectivos)


def crear_llave(
    db: Session,
    *,
    sistema: str,
    nombre_usuario_responsable: str,
    alcance: str,
    id_usuario_responsable: int | None = None,
    dias_expiracion: int | None = None,
) -> LlaveApiCreada:
    """Crea una nueva llave de API.

    La vigencia solicitada nunca puede superar el máximo permitido por
    política de seguridad (`LLAVE_API_DIAS_EXPIRACION_MAXIMO`).
    """
    dias = min(dias_expiracion or settings.LLAVE_API_DIAS_EXPIRACION_MAXIMO, settings.LLAVE_API_DIAS_EXPIRACION_MAXIMO)

    ahora = ahora_utc()
    clave_plana, clave_hash = _generar_par_de_llave(sistema)

    llave = LlaveApiModel(
        sistema=sistema,
        id_usuario_responsable=id_usuario_responsable,
        nombre_usuario_responsable=nombre_usuario_responsable,
        clave_hash=clave_hash,
        alcance=alcance,
        activa=True,
        fecha_creacion=ahora,
        fecha_expiracion=ahora + timedelta(days=dias),
        fecha_ultima_actualizacion=ahora,
    )
    db.add(llave)
    db.commit()
    db.refresh(llave)

    return LlaveApiCreada(
        id=llave.id,
        sistema=llave.sistema,
        nombre_usuario_responsable=llave.nombre_usuario_responsable,
        alcance=llave.alcance,
        fecha_expiracion=llave.fecha_expiracion,
        clave_api=clave_plana,
    )


def rotar_llave(db: Session, *, llave: LlaveApiModel, dias_expiracion: int | None = None) -> LlaveApiCreada:
    """Genera una nueva llave para el mismo registro (mismo sistema y responsable).

    Se utiliza cuando el ciclo de vigencia se cumple o cuando el responsable
    reporta la pérdida de la llave anterior. Los contadores de uso se
    reinician porque corresponden a un secreto físicamente distinto.
    """
    dias = min(dias_expiracion or settings.LLAVE_API_DIAS_EXPIRACION_MAXIMO, settings.LLAVE_API_DIAS_EXPIRACION_MAXIMO)

    ahora = ahora_utc()
    clave_plana, clave_hash = _generar_par_de_llave(llave.sistema)

    llave.clave_hash = clave_hash
    llave.activa = True
    llave.fecha_creacion = ahora
    llave.fecha_expiracion = ahora + timedelta(days=dias)
    llave.fecha_ultima_actualizacion = ahora
    llave.fecha_ultimo_uso = None
    llave.fecha_contador_diario = None
    llave.llamados_hoy = 0
    llave.total_llamados = 0

    db.commit()
    db.refresh(llave)

    return LlaveApiCreada(
        id=llave.id,
        sistema=llave.sistema,
        nombre_usuario_responsable=llave.nombre_usuario_responsable,
        alcance=llave.alcance,
        fecha_expiracion=llave.fecha_expiracion,
        clave_api=clave_plana,
    )


def registrar_uso(db: Session, llave: LlaveApiModel) -> None:
    """Actualiza los contadores de uso de una llave tras una validación exitosa."""
    hoy = date.today()

    if llave.fecha_contador_diario != hoy:
        llave.fecha_contador_diario = hoy
        llave.llamados_hoy = 1
    else:
        llave.llamados_hoy += 1

    llave.total_llamados += 1
    llave.fecha_ultimo_uso = ahora_utc()
    db.commit()


def validar_llave(db: Session, *, clave_plana: str, alcance_requerido: str) -> InformacionAutenticacion:
    """Valida una llave de API y su alcance, y registra el uso si es exitosa.

    El alcance requerido se compara contra los alcances *expandidos* de la
    llave (ver `_expandir_alcances`): una llave con solo `colaboradores:costos`
    sí satisface una operación que exige `colaboradores:basico`, porque
    costos es un superconjunto de básico, no un permiso paralelo.

    Lanza una excepción de dominio cuando la validación falla. Si la llave
    llegó a identificarse en la base de datos (existe, aunque esté
    revocada, expirada, o le falte alcance), la excepción lleva su
    identidad adjunta, para que el intento fallido quede trazado igual que
    uno exitoso.
    """
    fila = db.query(LlaveApiModel).filter(LlaveApiModel.clave_hash == _hashear(clave_plana)).first()

    if fila is None:
        raise LlaveApiInvalidaError("La API Key no existe")

    identidad = {
        "identificador_llave": fila.id,
        "sistema": fila.sistema,
        "responsable": fila.nombre_usuario_responsable,
    }

    if not fila.activa:
        raise LlaveApiInvalidaError("La API Key fue revocada", **identidad)

    if fila.fecha_expiracion <= ahora_utc():
        raise LlaveApiExpiradaError("La API Key expiró; debe rotarse antes de continuar en uso", **identidad)

    alcances = _expandir_alcances([alcance.strip() for alcance in fila.alcance.split(",")])
    if alcance_requerido not in alcances:
        raise AlcanceInsuficienteError(alcance_requerido, **identidad)

    registrar_uso(db, fila)

    return InformacionAutenticacion(
        identificador_llave=fila.id,
        sistema=fila.sistema,
        responsable=fila.nombre_usuario_responsable,
        alcances=alcances,
    )
