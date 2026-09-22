"""Llaves de acceso de los sistemas consumidores como Power BI, ZLHub, SGA, etc.

Cada llave tiene un ciclo de vida completo, vigencia con fecha de
expiración, responsable a quien fue entregada y contadores de uso que
permiten detectar patrones anómalos de consumo.
"""
from datetime import date, datetime

from sqlalchemy import Boolean, Date, DateTime, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.shared.tiempo import ahora_utc


class LlaveApiModel(Base):
    __tablename__ = "seguridad_llaves_api"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)

    # Sistema propietario de la llave ejemplo power_bi, zlhub, sga
    sistema: Mapped[str] = mapped_column(String(100), nullable=False, index=True)

    # Persona responsable a quien se entrega la llave. 
    # id_usuario_responsable queda nulo por ahora y se vinculará a una tabla de usuarios cuando exista.
    # nombre_usuario_responsable identifica al responsable mientras tanto.
    id_usuario_responsable: Mapped[int | None] = mapped_column(Integer, nullable=True)
    nombre_usuario_responsable: Mapped[str] = mapped_column(String(200), nullable=False)

    # Hash de la llave, el valor en texto plano nunca se almacena.
    clave_hash: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)

    # Uno o varios alcances separados por coma "colaboradores:basico, colaboradores:costos".
    alcance: Mapped[str] = mapped_column(String(255), nullable=False)

    activa: Mapped[bool] = mapped_column(Boolean, default=True)

    # Vigencia toda llave expira. La política vigente exige un máximo de 180 días.
    fecha_creacion: Mapped[datetime] = mapped_column(DateTime, default=ahora_utc)
    fecha_expiracion: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    fecha_ultima_actualizacion: Mapped[datetime] = mapped_column(
        DateTime, default=ahora_utc
    )

    # cuándo fue la última vez que se usó, cuántas veces se ha llamado hoy y 
    # cuántas veces se ha llamado en total desde su creación.
    fecha_ultimo_uso: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    fecha_contador_diario: Mapped[date | None] = mapped_column(Date, nullable=True)
    llamados_hoy: Mapped[int] = mapped_column(Integer, default=0)
    total_llamados: Mapped[int] = mapped_column(Integer, default=0)

