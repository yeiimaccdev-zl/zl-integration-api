"""Constantes compartidas por toda la aplicación.

Centralizar estos valores evita "números y cadenas mágicas" repetidas en
distintos módulos y deja en un solo lugar las reglas de negocio que varios
componentes necesitan conocer.
"""

# Alcances (scopes) reconocidos por el sistema de autenticación.
ALCANCE_COLABORADORES_BASICO = "colaboradores:basico"
ALCANCE_COLABORADORES_COSTOS = "colaboradores:costos"

# Jerarquía de alcances: "costos" es un superconjunto de "básico", no un
# permiso paralelo. Una llave con alcance de costos puede usar cualquier
# endpoint que exija el alcance básico, sin necesidad de que ambos estén
# listados explícitamente en la llave. La relación es unidireccional: tener
# el alcance básico nunca otorga el de costos.
JERARQUIA_ALCANCES: dict[str, frozenset[str]] = {
    ALCANCE_COLABORADORES_COSTOS: frozenset({ALCANCE_COLABORADORES_BASICO, ALCANCE_COLABORADORES_COSTOS}),
}

# Vigencia máxima permitida para una llave de API, por política de seguridad.
DIAS_EXPIRACION_MAXIMO_LLAVE_API = 180

# Prefijo de llave por sistema consumidor: permite identificar a simple vista
# el dueño de una llave (por ejemplo en logs de auditoría) sin que eso
# reemplace la validación real, que siempre ocurre contra el hash almacenado.
# Los sistemas no listados aquí reciben el prefijo genérico "zl-ext".
PREFIJOS_LLAVE_POR_SISTEMA: dict[str, str] = {
    "sga": "zl-sga",
    "power_bi": "zl-bi",
    "zlhub": "zl-hub",
}
PREFIJO_LLAVE_GENERICO = "zl-ext"

# Categorías de error para clasificar los registros de auditoría y facilitar
# la construcción de reportes e indicadores de seguridad.
CATEGORIA_ERROR_AUTENTICACION = "AUTENTICACION"
CATEGORIA_ERROR_AUTORIZACION = "AUTORIZACION"
CATEGORIA_ERROR_VALIDACION_INPUT = "VALIDACION_INPUT"
CATEGORIA_ERROR_DISPONIBILIDAD_PROSOFT = "DISPONIBILIDAD_PROSOFT"
CATEGORIA_ERROR_SIN_RESULTADO = "SIN_RESULTADO"
CATEGORIA_ERROR_INTERNO = "ERROR_INTERNO"

# Longitudes máximas para los campos de auditoría alimentados por datos que
# el propio consumidor controla (encabezados HTTP) y que, por lo tanto,
# deben tratarse como no confiables.
LONGITUD_MAXIMA_PREFIJO_LLAVE_AUDITADO = 10
LONGITUD_MAXIMA_AGENTE_USUARIO_AUDITADO = 255
LONGITUD_MAXIMA_PARAMETROS_CONSULTA_AUDITADOS = 500
