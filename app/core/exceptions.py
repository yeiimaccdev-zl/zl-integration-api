"""Traducción de las excepciones de dominio app.shared.excepciones a
respuestas HTTP.

construir la respuesta que recibe el consumidor, 
dejar en request.state todo lo que el middleware de auditoría necesita para que el intento quede completamente
trazado comoo mensaje de error, categoria, y la identidad del sistema cuando la excepción la trae adjunta. 
"""
from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.shared.constantes import (
    CATEGORIA_ERROR_AUTENTICACION,
    CATEGORIA_ERROR_AUTORIZACION,
    CATEGORIA_ERROR_DISPONIBILIDAD_PROSOFT,
    CATEGORIA_ERROR_SIN_RESULTADO,
    CATEGORIA_ERROR_VALIDACION_INPUT,
)
from app.shared.excepciones import (
    AlcanceInsuficienteError,
    ErrorLlaveApiConIdentidad,
    FuenteExternaNoDisponibleError,
    ParametroInvalidoError,
    RecursoNoEncontradoError,
)


def _registrar_contexto_error(request: Request, *, mensaje: str, categoria: str) -> None:
    request.state.mensaje_error = mensaje
    request.state.categoria_error = categoria


def _propagar_identidad_si_existe(request: Request, exc: ErrorLlaveApiConIdentidad) -> None:
    """Si la excepción trae la identidad de una llave que sí fue encontrada en la
    base de datos, la deja en request.state para que la auditoría no la pierda,
    aunque la solicitud haya sido rechazada."""
    if exc.sistema is not None:
        request.state.sistema_consumidor = exc.sistema
        request.state.identificador_llave_api = exc.identificador_llave
        request.state.responsable_llave_api = exc.responsable


def registrar_manejadores_excepciones(app: FastAPI) -> None:
    @app.exception_handler(ErrorLlaveApiConIdentidad)
    async def _manejar_error_autenticacion(request: Request, exc: ErrorLlaveApiConIdentidad) -> JSONResponse:
        _registrar_contexto_error(request, mensaje=str(exc), categoria=CATEGORIA_ERROR_AUTENTICACION)
        _propagar_identidad_si_existe(request, exc)
        return JSONResponse(status_code=status.HTTP_401_UNAUTHORIZED, content={"detalle": str(exc)})

    @app.exception_handler(AlcanceInsuficienteError)
    async def _manejar_alcance_insuficiente(request: Request, exc: AlcanceInsuficienteError) -> JSONResponse:
        _registrar_contexto_error(request, mensaje=str(exc), categoria=CATEGORIA_ERROR_AUTORIZACION)
        _propagar_identidad_si_existe(request, exc)
        return JSONResponse(status_code=status.HTTP_403_FORBIDDEN, content={"detalle": str(exc)})

    @app.exception_handler(ParametroInvalidoError)
    async def _manejar_parametro_invalido(request: Request, exc: ParametroInvalidoError) -> JSONResponse:
        _registrar_contexto_error(request, mensaje=str(exc), categoria=CATEGORIA_ERROR_VALIDACION_INPUT)
        return JSONResponse(status_code=status.HTTP_400_BAD_REQUEST, content={"detalle": str(exc)})

    @app.exception_handler(RequestValidationError)
    async def _manejar_error_validacion_fastapi(request: Request, exc: RequestValidationError) -> JSONResponse:
        # Errores de validacion resueltos por FastAPI antes de que la
        # solicitud llegue a una funcion operativa, como un tipo de dato
        # incorrecto en un parametro.
        _registrar_contexto_error(request, mensaje=str(exc), categoria=CATEGORIA_ERROR_VALIDACION_INPUT)
        return JSONResponse(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, content={"detalle": exc.errors()})

    @app.exception_handler(RecursoNoEncontradoError)
    async def _manejar_recurso_no_encontrado(request: Request, exc: RecursoNoEncontradoError) -> JSONResponse:
        _registrar_contexto_error(request, mensaje=str(exc), categoria=CATEGORIA_ERROR_SIN_RESULTADO)
        return JSONResponse(status_code=status.HTTP_404_NOT_FOUND, content={"detalle": str(exc)})

    @app.exception_handler(FuenteExternaNoDisponibleError)
    async def _manejar_fuente_no_disponible(request: Request, exc: FuenteExternaNoDisponibleError) -> JSONResponse:
        _registrar_contexto_error(
            request,
            mensaje=str(exc),
            categoria=CATEGORIA_ERROR_DISPONIBILIDAD_PROSOFT,
        )
        return JSONResponse(
            status_code=status.HTTP_502_BAD_GATEWAY,
            content={"detalle": "No fue posible completar la consulta en este momento"},
        )
