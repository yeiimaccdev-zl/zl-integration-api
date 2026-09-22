"""Excepciones de dominio.

Estas clases no dependen de FastAPI ni de ningún detalle HTTP: representan
condiciones de negocio. La traducción a una respuesta HTTP concreta ocurre
en `app.core.exceptions`, que registra un manejador por cada una de ellas.

Las excepciones relacionadas con una llave de API que SÍ llegó a
identificarse en la base de datos (revocada, expirada, o sin el alcance
requerido) llevan además la identidad del sistema que la usó. Esto es
deliberado: una solicitud rechazada no debe perder trazabilidad. El
middleware de auditoría lee estos atributos para que un intento fallido
quede tan identificado como uno exitoso.
"""


class ErrorDominio(Exception):
    """Excepción base de la que heredan todos los errores de negocio de la aplicación."""


class ErrorLlaveApiConIdentidad(ErrorDominio):
    """Base común para errores de una llave que sí fue encontrada en la base de datos."""

    def __init__(
        self,
        mensaje: str,
        *,
        identificador_llave: int | None = None,
        sistema: str | None = None,
        responsable: str | None = None,
    ) -> None:
        self.identificador_llave = identificador_llave
        self.sistema = sistema
        self.responsable = responsable
        super().__init__(mensaje)


class LlaveApiInvalidaError(ErrorLlaveApiConIdentidad):
    """La API Key recibida no existe, no fue enviada, o fue revocada.

    Cuando la llave sí existe en la base de datos pero está revocada, se
    construye con la identidad del sistema al que pertenecía, precisamente
    porque el uso de una llave revocada es en sí mismo un evento de
    seguridad relevante que debe quedar identificado.
    """


class LlaveApiExpiradaError(ErrorLlaveApiConIdentidad):
    """La API Key recibida superó su fecha de expiración."""


class AlcanceInsuficienteError(ErrorLlaveApiConIdentidad):
    """La API Key es válida, pero no tiene el alcance requerido para la operación."""

    def __init__(
        self,
        alcance_requerido: str,
        *,
        identificador_llave: int | None = None,
        sistema: str | None = None,
        responsable: str | None = None,
    ) -> None:
        self.alcance_requerido = alcance_requerido
        super().__init__(
            f"Se requiere el alcance '{alcance_requerido}'",
            identificador_llave=identificador_llave,
            sistema=sistema,
            responsable=responsable,
        )


class ParametroInvalidoError(ErrorDominio):
    """Un parámetro de entrada no cumple una regla de negocio (no es un error de formato HTTP)."""


class RecursoNoEncontradoError(ErrorDominio):
    """La operación es válida, pero el recurso solicitado no existe."""


class FuenteExternaNoDisponibleError(ErrorDominio):
    """No fue posible completar la consulta contra una fuente de datos externa (por ejemplo, Prosoft)."""
