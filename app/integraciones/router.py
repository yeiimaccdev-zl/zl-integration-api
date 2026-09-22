"""Agrupa, bajo un único prefijo `/integraciones`, los routers de cada
sistema de terceros que consume el proyecto.

Cada submódulo de `integraciones/` (`prosoft/`, y en el futuro `avansat/`,
etc.) define su propio router con su prefijo local (ej. `/colaboradores`).
Este archivo es el único lugar que conoce la lista completa de
integraciones activas: agregar una nueva integración es agregar dos líneas
aquí, sin tocar `app/main.py` ni el router raíz de la API.
"""
from fastapi import APIRouter

from app.integraciones.prosoft.router import router as prosoft_router

router = APIRouter(prefix="/integraciones")

router.include_router(prosoft_router)

# Futuras integraciones se agregan siguiendo el mismo patrón, ej.:
# from app.integraciones.avansat.router import router as avansat_router
# router.include_router(avansat_router)
