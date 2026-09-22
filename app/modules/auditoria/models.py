"""Registro de auditoria de solicitudes.

Esta tabla es de solo escritura desde la aplicacion, no existe ninguna
operación de actualización ni de borrado sobre sus registros. Es el
requisito minimo para que la auditoria sea confiable ante una revisión
externa, un registro que puede modificarse después de creado no sirve
como evidencia.

Cada fila responde por si sola, a las preguntas tipicas de una
investigación: qué se consultó, quién lo hizO, si el intento
falló, desde dónde, cuánto tardó, cuántos datos devolvió, y cuál fue el
resultado.
"""
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.shared.tiempo import ahora_utc


class RegistroAuditoriaModel(Base):
    __tablename__ = "auditoria_solicitudes"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)

    # Correlación: qué solicitud puntual y desde qué servicio.
    identificador_solicitud: Mapped[str] = mapped_column(String(36), index=True)
    servicio: Mapped[str] = mapped_column(String(80), index=True)

    # Qué se solicitó.
    metodo_http: Mapped[str] = mapped_column(String(10))
    ruta: Mapped[str] = mapped_column(String(255))
    parametros_consulta: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Quién lo solicitó. Se completa incluso cuando la solicitud es
    # rechazada, siempre que la llave utilizada haya llegado a
    # identificarse en la base de datos.
    # El nombre del responsable se guarda como una copia tomada en el
    # momento de la solicitud, no como referencia a la llave, para que el
    # registro histórico no cambie si la llave se rota más adelante.
    sistema_consumidor: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)
    identificador_llave_api: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    responsable_llave_api: Mapped[str | None] = mapped_column(String(200), nullable=True)

    # Prefijo saneado de la llave recibida, capturado siempre que llegó un
    # encabezado X-API-Key, exista o no una llave real detrás de él. Permite
    # rastrear intentos de acceso con llaves inexistentes o mal formadas sin
    # almacenar el secreto completo.
    prefijo_llave_intentada: Mapped[str | None] = mapped_column(String(20), nullable=True)

    # Origen de la solicitud.
    ip_origen: Mapped[str | None] = mapped_column(String(45), nullable=True)
    ip_real_cliente: Mapped[str | None] = mapped_column(String(255), nullable=True)
    agente_usuario: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # Resultado de la solicitud.
    codigo_respuesta: Mapped[int] = mapped_column(Integer)
    exitosa: Mapped[bool] = mapped_column(Boolean)
    categoria_error: Mapped[str | None] = mapped_column(String(50), nullable=True)
    mensaje_error: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Volumen de datos devuelto, indispensable para detectar descargas masivas .
    tamano_respuesta_bytes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    cantidad_registros: Mapped[int | None] = mapped_column(Integer, nullable=True)

    duracion_ms: Mapped[float] = mapped_column(Float)

    # Momento exacto de inicio y fin, además de la duración ya calculada,
    # porque una investigación puede requerir el instante preciso, no solo
    # cuánto tardó.
    fecha_hora_inicio: Mapped[datetime] = mapped_column(DateTime, default=ahora_utc, index=True)
    fecha_hora_fin: Mapped[datetime] = mapped_column(DateTime, default=ahora_utc)
