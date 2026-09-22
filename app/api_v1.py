"""Router raíz de la versión 1 de la API pública (`/api/v1`).

Combina, bajo un único prefijo versionado, los dos grandes grupos de
routers del proyecto:
- `integraciones/` → sistemas de terceros (Prosoft, y en el futuro Avansat, etc.)
- `modules/`       → módulos de negocio propios del SGA, expuestos bajo `/sga`

Versionar en un único punto (en vez de repetir el prefijo en cada router
individual) permite introducir una `/api/v2` el día que se necesite sin
tocar cada módulo uno por uno, y evita que `app/main.py` tenga que conocer
cada router de negocio por separado.

Rutas resultantes, por ejemplo:
- `/api/v1/integraciones/colaboradores`
- `/api/v1/sga/transporte/solicitudes` (una vez exista ese módulo)
"""
from fastapi import APIRouter

from app.integraciones.router import router as integraciones_router
from app.modules.router import router as modulos_sga_router

router = APIRouter(prefix="/api/v1")

router.include_router(integraciones_router)
router.include_router(modulos_sga_router)
