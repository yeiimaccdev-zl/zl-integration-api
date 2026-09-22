"""Agrupa, bajo un único prefijo `/sga`, los routers de los módulos de
negocio propios del Sistema de Gestión de Actividades.

`modules/` también contiene módulos de infraestructura interna
(`seguridad/`, `auditoria/`) que no exponen endpoints HTTP propios — esos
no se registran aquí, se usan directamente desde `core/` y desde los
routers que sí exponen rutas. Este archivo solo agrupa los módulos de
negocio, ej. `transporte/` cuando se implemente.

Agregar un módulo nuevo del SGA es agregar dos líneas aquí, sin tocar
`app/main.py` ni el router raíz de la API.
"""
from fastapi import APIRouter

router = APIRouter(prefix="/sga")

# Los módulos de negocio del SGA se agregan aquí a medida que se
# implementan, siguiendo el mismo patrón que app/integraciones/router.py, ej.:
# from app.modules.transporte.router import router as transporte_router
# router.include_router(transporte_router)
