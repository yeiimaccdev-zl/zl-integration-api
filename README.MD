# zl-integration-api

API de integraciones de Zona Logística. Consolida los datos de
colaboradores a partir de Prosoft, en reemplazo de las consultas que antes
se resolvían contra las APIs de Buk. Es la base sobre la que más adelante
se construirán los demás módulos del SGA (Sistema de Gestión de
Actividades); por ahora, su función principal y su fortaleza es esta capa
de integración.

Construida con FastAPI. La documentación interactiva (Swagger UI) queda
disponible en `/docs` una vez el servicio está en ejecución, y es la
referencia autorizada de cada endpoint, sus parámetros y sus esquemas de
respuesta.

## Arquitectura

La aplicación se organiza en capas con responsabilidades claras, siguiendo
principios de arquitectura limpia: la lógica de negocio (`servicio.py` en
cada módulo) no depende de FastAPI ni de SQLAlchemy directamente en sus
decisiones; los detalles de framework y de persistencia quedan en los
bordes (`core/`, `models.py`).

```
app/
├── main.py                          # Único archivo en la raíz de app/: ensambla la aplicación
├── api_v1.py                        # Router raíz /api/v1: agrupa integraciones/ y modules/ (sga)
├── core/                            # Infraestructura transversal, usada por todos los módulos
│   ├── config.py                     # Configuración desde variables de entorno
│   ├── cors.py                       # CORS con política distinta por prefijo de ruta
│   ├── database.py                   # Conexión a MySQL (propia) y a Prosoft (externa)
│   ├── exceptions.py                  # Traducción de excepciones de dominio a respuestas HTTP
│   ├── logging.py                     # Logging estructurado en JSON
│   ├── middleware.py                  # Middleware de correlación y auditoría de cada solicitud
│   └── security.py                    # Dependencia de FastAPI para exigir API Key + alcance
├── integraciones/
│   ├── router.py                     # Agrupa los routers de terceros bajo /integraciones
│   └── prosoft/
│       ├── client.py                   # Consulta parametrizada contra Prosoft (SQL Server)
│       ├── mapper.py                   # Capa anti-corrupción: fila cruda -> esquema de salida
│       ├── schemas.py                  # Esquemas de respuesta (básico / con costos)
│       └── router.py                   # Endpoints de colaboradores (prefijo local /colaboradores)
├── modules/
│   ├── router.py                     # Agrupa los routers de negocio del SGA bajo /sga
│   ├── seguridad/
│   │   ├── models.py                    # Llave de API: ciclo de vida completo
│   │   ├── schemas.py                    # Esquema de una llave recién creada o rotada
│   │   └── servicio.py                   # Creación, validación, uso y rotación de llaves
│   └── auditoria/
│       ├── models.py                     # Registro de auditoría de nivel forense
│       └── servicio.py                    # Única función de escritura del historial de auditoría
└── shared/                           # Utilidades sin dependencias de framework
    ├── constantes.py                  # Alcances, categorías de error y límites de seguridad
    ├── excepciones.py                 # Excepciones de dominio (algunas con identidad adjunta)
    ├── saneamiento.py                  # Limpieza de entradas no confiables antes de auditar
    └── tiempo.py                      # Manejo consistente de fechas en UTC

alembic/
├── env.py                            # Configuración de Alembic, reutiliza app.core.config
└── versions/
    └── 0001_esquema_inicial.py        # Migración base: llaves de API y auditoría

scripts/
├── lib/
│   └── Comun.ps1                     # Funciones compartidas: salud, backup MySQL, swap de release
├── configurar_estructura.ps1          # Prepara carpetas en el servidor (una sola vez)
├── instalar_servicio_windows.ps1      # Registra el servicio de Windows con NSSM (una sola vez)
├── desplegar.ps1                      # Despliega un commit: release, backup, migración, pruebas, swap, rollback automático
├── rollback.ps1                       # Rollback manual a una release anterior
├── seed_api_keys.py                  # Crea las llaves de API iniciales
└── rotar_llave.py                     # Rota la llave de un sistema (ciclo cumplido o pérdida)

.github/workflows/
└── despliegue.yml                    # CI en cada push/PR, CD a producción en cada push a main

DESPLIEGUE_WINDOWS_SERVER_2022.md     # Procedimiento completo de despliegue, paso a paso

test/
├── conftest.py                       # Base de datos en memoria para las pruebas
├── test_seguridad_servicio.py         # Creación, expiración, alcances y rotación de llaves
├── test_auditoria_servicio.py         # Registro de auditoría
├── test_prosoft_client.py             # Traducción de filtros hacia Prosoft
├── test_router_colaboradores.py       # Endpoints de extremo a extremo, incluida la auditoría
├── test_cors.py                      # Política de CORS distinta por prefijo de ruta
└── test_main.py                      # Health check real y restricción de documentación
```

### Prefijos de ruta y versionado (`/api/v1`)

Ningún router de negocio declara `/api/v1` ni su grupo (`/integraciones`,
`/sga`) como prefijo propio — cada uno solo conoce su nombre local (ej.
`prosoft/router.py` usa `/colaboradores`). El prefijo completo se arma por
composición, en tres niveles:

1. `app/integraciones/router.py` agrupa cada integración de terceros bajo
   `/integraciones` (ej. `prosoft` → `/integraciones/colaboradores`).
2. `app/modules/router.py` agrupa cada módulo de negocio del SGA bajo
   `/sga` (ej. un futuro módulo `transporte` → `/sga/transporte`).
3. `app/api_v1.py` agrupa ambos bajo `/api/v1`, y es lo único que
   `app/main.py` incluye directamente.

Resultado: `GET /api/v1/integraciones/colaboradores`,
`GET /api/v1/sga/transporte/solicitudes` (cuando ese módulo exista), etc.

Agregar una integración o un módulo nuevo es registrarlo en el agregador
correspondiente (una línea de `import` + una de `include_router`) —
`app/main.py` y `app/api_v1.py` no cambian. El día que se necesite una
`/api/v2`, se crea un `app/api_v2.py` análogo y se incluye junto al de v1
en `main.py`, sin reescribir los routers de negocio existentes.



### Por qué está organizado así

- **`core/` es infraestructura, no negocio.** Nada específico de
  colaboradores, llaves o auditoría vive aquí — solo lo que cualquier
  módulo futuro del SGA también va a necesitar (conexión a base de datos,
  logging, manejo de errores, autenticación).
- **Cada módulo de negocio tiene su propio `servicio.py`.** Ahí vive la
  lógica real (por ejemplo, que una llave no pueda expirar en más de 180
  días); los routers y los modelos ORM son detalles de implementación
  alrededor de esa lógica, no el lugar donde vive.
- **`shared/` no depende de nada del resto de la aplicación.** Se puede
  copiar tal cual a cualquier otro servicio del SGA sin arrastrar
  referencias a Prosoft, a MySQL o a FastAPI.
- **El esquema de base de datos se gestiona con Alembic, no con
  `create_all()`**, salvo en desarrollo por conveniencia. Es la diferencia
  entre un cambio de esquema controlado y versionado, y uno que ocurre en
  silencio la próxima vez que alguien reinicie el proceso.

## Seguridad: llaves de API

Los sistemas consumidores se autentican con una API Key enviada en el
encabezado `X-API-Key`. Cada llave incluye un **prefijo identificador del
sistema propietario** (`zl-sga_`, `zl-bi_`, `zl-hub_`, o `zl-ext_` para
sistemas no registrados en el mapa de prefijos), útil para reconocerla a
simple vista en herramientas de gestión — la validación real, sin embargo,
siempre ocurre contra el hash almacenado, nunca contra el prefijo.

Cada llave tiene además:

- Uno o varios **alcances**, separados por coma (`colaboradores:basico`,
  `colaboradores:costos`). Son **jerárquicos, no paralelos**: `costos` es
  un superconjunto de `basico` (ver `JERARQUIA_ALCANCES` en
  `app/shared/constantes.py`), así que una llave nunca necesita listar
  ambos — basta con `alcance="colaboradores:costos"` para que, en la
  práctica, tenga también el básico. Eso tiene dos efectos distintos y
  vale la pena no confundirlos:
  - **Acceso**: un endpoint que exige básico como mínimo (`requerir_alcance_minimo`,
    en `app/core/security.py`) deja pasar igual a una llave que solo tiene
    costos. La relación es unidireccional: básico nunca otorga costos.
  - **Contenido de la respuesta**: el nivel de detalle se ajusta según el
    alcance real de la llave, no según el mínimo exigido por la ruta — un
    sistema con alcance de costos recibe salario y auxilio de transporte
    tanto en el listado como en el detalle individual (incluso llamando al
    endpoint "básico"); uno con solo el alcance básico recibe únicamente
    los datos generales.
- Un **responsable** a quien fue entregada (`nombre_usuario_responsable`;
  `id_usuario_responsable` queda nulo hasta que exista una tabla de
  usuarios a la cual vincularlo).
- Una **vigencia con fecha de expiración**, de máximo 180 días por
  política de seguridad. Una llave expirada es rechazada aunque siga
  marcada como activa.
- **Contadores de uso**: fecha del último uso, llamados del día en curso y
  total histórico de llamados — información que permite detectar un
  consumo anómalo.

Cuando el ciclo de vigencia se cumple o el responsable reporta la pérdida
de una llave, se ejecuta `scripts/rotar_llave.py`: genera un nuevo valor
para el mismo registro (mismo sistema, mismo responsable) y reinicia sus
contadores. La llave anterior deja de ser válida de inmediato.

Las llaves se almacenan únicamente como hash; el valor en texto plano se
entrega una sola vez, en el momento de crearlas o rotarlas.

## CORS

CORS es una restricción que aplica el **navegador**, no el servidor: no
afecta a los consumidores servidor-a-servidor (Power BI, otro backend, una
automatización, curl/Postman). Solo importa cuando código JavaScript,
corriendo en una página web, llama directo a esta API desde un origen
distinto.

Como distintos módulos pueden necesitar distintos orígenes autorizados
(ej. `integraciones/colaboradores` para un consumidor, `sga/transporte`
para otro), el proyecto no usa el `CORSMiddleware` estándar de
FastAPI/Starlette —que solo admite una única política global— sino un
middleware propio (`app/core/cors.py`, `MiddlewareCorsPorModulo`) que
aplica la política del prefijo de ruta más específico que coincida con
cada solicitud.

Se configura con la variable de entorno `CORS_POLITICAS`, un JSON que
mapea un prefijo de ruta a su política:

```
CORS_POLITICAS={"/api/v1/integraciones/colaboradores": {"origenes": ["https://zlhub.zonalogistica.com.co"]}, "/api/v1/sga/transporte": {"origenes": ["https://sga.zonalogistica.com.co", "http://localhost:5173"], "metodos": ["GET", "POST"]}}
```

Cada política acepta:

| Campo | Descripción |
|---|---|
| `origenes` | Lista de orígenes exactos autorizados (`esquema://host:puerto`, sin barra final). Obligatorio, mínimo un valor. **No se admite `"*"`**: estos endpoints pueden exponer datos operativos de colaboradores, así que cada origen debe declararse explícitamente. |
| `metodos` | Métodos HTTP permitidos en la solicitud real. Por defecto `["GET"]`. |
| `encabezados` | Encabezados que el navegador puede enviar. Por defecto `["Content-Type", "X-API-Key"]`. Si un módulo se llama desde el navegador con `X-API-Key`, ese encabezado debe estar en esta lista o el preflight lo rechaza. |
| `credenciales` | Si se aceptan cookies/credenciales de navegador. Por defecto `false`; no tiene sentido activarlo mientras la autenticación sea por `X-API-Key` explícito. |

Por defecto `CORS_POLITICAS` es `{}`: ninguna ruta tiene política, así que
ningún origen de navegador puede leer las respuestas hasta que se declare
explícitamente aquí — mismo criterio de "fallar cerrado" que el resto de
la configuración del proyecto.

**Advertencia de seguridad para quien active esto en un módulo nuevo:**
enviar la API Key desde JavaScript de navegador la deja visible en el
código fuente y en la pestaña de red del cliente. CORS controla qué
origen puede *leer* la respuesta, no oculta ni protege ese secreto. Para
un módulo pensado para llamarse directo desde el navegador, conviene
evaluar si el dato expuesto justifica ese riesgo, o si es mejor que el
frontend hable con su propio backend y sea ese backend quien llame a
`zl-integration-api` con la API Key real — coherente con el principio de
"único punto de integración" del proyecto.

## Auditoría

Cada solicitud atendida por la API queda registrada en la tabla
`auditoria_solicitudes`, con estándar de nivel forense, pensado para
resistir una auditoría externa (ISO 27001 u otra) o una investigación
legal:

- **Qué se consultó**: ruta y parámetros de búsqueda.
- **Quién lo hizo**: sistema consumidor, identificador de la llave
  utilizada y su responsable. Esta identidad se registra **incluso cuando
  la solicitud es rechazada** — una llave revocada, expirada, o sin el
  alcance necesario deja su identidad en el registro igual que una
  solicitud exitosa, porque un intento fallido con una llave real es un
  evento de seguridad tan relevante como uno exitoso. Cuando la llave ni
  siquiera llega a identificarse (no existe, o la solicitud no trae
  ninguna), queda al menos su `prefijo_llave_intentada`, una versión
  saneada y truncada de lo recibido, suficiente para detectar patrones de
  exploración sin almacenar ningún secreto.
- **Desde dónde**: `ip_origen` (la mejor IP resuelta, priorizando
  `X-Forwarded-For` sobre la conexión TCP directa), `ip_real_cliente` (el
  valor completo de ese encabezado, con toda la cadena de proxies si la
  hubo) y el agente de usuario, saneado para prevenir inyección en logs.
  `X-Forwarded-For` es un encabezado que el propio cliente puede enviar
  y por lo tanto es falsificable, a menos que el proxy reverso (IIS) esté
  configurado para **sobrescribirlo**, no anexarlo, en cada solicitud
  entrante — esa configuración debe confirmarse con el equipo de TI antes
  de tratar este valor como prueba definitiva de origen.
- **Cuándo**: inicio y fin exactos de la solicitud, además de la duración
  ya calculada.
- **Con qué resultado**: código de respuesta, si fue exitosa, una
  **categoría de error** (`AUTENTICACION`, `AUTORIZACION`,
  `VALIDACION_INPUT`, `DISPONIBILIDAD_PROSOFT`, `SIN_RESULTADO`,
  `ERROR_INTERNO`) y el mensaje descriptivo correspondiente — poblado para
  **todos** los tipos de error, no solo para las fallas de Prosoft.
- **Cuánto devolvió**: tamaño de la respuesta en bytes y cantidad de
  registros, para detectar descargas masivas o intentos de exfiltración.

El historial es de solo escritura: no existe ninguna operación de
actualización ni de borrado sobre estos registros, condición necesaria
para que sirvan como evidencia ante una revisión externa. El módulo está
diseñado para ser reutilizado por los demás servicios del SGA a medida que
se incorporen, cada uno identificándose con su propio nombre de servicio.

## Endpoints

| Método | Ruta | Alcance requerido | Descripción |
|---|---|---|---|
| GET | `/api/v1/integraciones/colaboradores` | `colaboradores:basico` | Lista colaboradores, con filtros por cédula, nombre y estado. |
| GET | `/api/v1/integraciones/colaboradores/{cedula}` | `colaboradores:basico` | Detalle de un colaborador. |
| GET | `/api/v1/integraciones/colaboradores/{cedula}/costos` | `colaboradores:costos` | Detalle con salario y auxilio de transporte. |
| GET | `/health` | — | Verificación de disponibilidad del servicio. |

La documentación completa de cada endpoint —parámetros, esquemas de
entrada y salida, y ejemplos— está en Swagger UI (`/docs`), generada
automáticamente a partir del código; es la fuente de verdad, no este
archivo.

## Uso rápido

En desarrollo: `cp .env.example .env`, completar las credenciales,
`pip install .` y `uvicorn app.main:app --reload`. La documentación
interactiva queda en `http://localhost:8000/docs`, desde donde se puede
probar cada endpoint directamente. Para consumir la API se necesita una
API Key (`scripts/seed_api_keys.py` genera las iniciales) enviada en el
encabezado `X-API-Key`; el nivel de detalle de la respuesta de
`/api/v1/integraciones/colaboradores` depende del alcance de esa llave.

En producción, el proceso es distinto en tres puntos clave: el esquema de
base de datos se aplica con `alembic upgrade head`, no automáticamente al
arrancar; la documentación interactiva queda deshabilitada; y el proceso
se registra como servicio de Windows para que sobreviva reinicios. El
detalle completo está en la sección [Despliegue a producción](#despliegue-a-producción).

## Instalación y puesta en marcha (desarrollo)

### Requisitos

- Python 3.12 o superior.
- Acceso de red hacia MySQL y hacia Prosoft (SQL Server, vía VPN).

### Pasos

```bash
# 1. Clonar el repositorio
git clone <url-del-repositorio>
cd zl-integration-api

# 2. Crear el entorno virtual e instalar dependencias
python -m venv .venv
.\.venv\Scripts\activate
pip install .

# 3. Configurar las variables de entorno
cp .env.example .env
# Completar MYSQL_DATABASE_URL y PROSOFT_DATABASE_URL con las credenciales reales.
# ENTORNO=desarrollo (valor por defecto) habilita /docs y la creación
# automática de tablas — ninguno de los dos ocurre en producción.

# 4. Ejecutar el servicio
uvicorn app.main:app --reload
```

La documentación interactiva queda disponible en
`http://localhost:8000/docs`.

### Generación de llaves de API

```bash
python scripts/seed_api_keys.py
```

Cada llave se imprime en texto plano una única vez. Debe guardarse de
inmediato en el gestor de credenciales del equipo.

### Rotación de una llave

```bash
python scripts/rotar_llave.py <sistema>
```

### Pruebas

```bash
pip install ".[dev]"
pytest
```

Las pruebas no requieren conexión a MySQL ni a Prosoft: usan una base de
datos en memoria y datos de prueba para la integración externa.

## Despliegue a producción

El detalle completo —qué instalar y habilitar en Google Cloud y en la VM,
IIS como proxy reverso, releases inmutables, backup y migración
automáticos, rollback en segundos si algo falla, y CI/CD con GitHub
Actions— está en
[`DESPLIEGUE_WINDOWS_SERVER_2022.md`](./DESPLIEGUE_WINDOWS_SERVER_2022.md).
Este README no repite ese contenido para no desincronizarse de él; aquí
solo el resumen de los mecanismos, para quien ya conoce el procedimiento
y necesita el comando exacto.

### Estructura en el servidor

```
C:\zl-integration-api\
├── repository\        # clon técnico, usado por desplegar.ps1 para crear releases
├── releases\
│   └── <fecha>-<sha>\  # una carpeta inmutable por despliegue, con su propio venv
├── current             # junction -> releases\<release activa>; IIS/NSSM siempre apuntan aquí
├── shared\
│   ├── .env              # credenciales reales, no se versiona, se copia a cada release nueva
│   └── backups\          # dump de MySQL antes de cada migración, con hash SHA-256
└── logs\
```

### Despliegue manual

```powershell
.\scripts\desplegar.ps1 -Commit <sha> -RepoUrl "https://github.com/<org>/zl-integration-api.git"
```

Crea la release, respalda MySQL, aplica migraciones, corre la suite de
pruebas **dentro de la release nueva antes de exponerla**, y solo entonces
cambia `current` y reinicia el servicio. Si `/health` no responde bien
después del cambio, revierte automáticamente a la release anterior sin
intervención manual.

### Rollback manual

```powershell
.\scripts\rollback.ps1 -Listar          # ver releases disponibles
.\scripts\rollback.ps1                  # volver a la inmediatamente anterior
.\scripts\rollback.ps1 -Release <nombre> # volver a una release específica
```

No revierte migraciones de base de datos — ver la advertencia en el
propio script y en el MD de despliegue antes de usarlo tras una release
que migró el esquema.

### CI/CD

Cada `push`/`pull request` corre pruebas y `ruff` en GitHub Actions
(`.github/workflows/despliegue.yml`). Cada `push` a `main`, tras pasar las
pruebas, dispara el despliegue automático en la VM a través de un
self-hosted runner registrado ahí — no se abre ningún puerto nuevo para
esto, el runner se conecta hacia GitHub, nunca al revés. Requiere
aprobación manual si el ambiente `produccion` está configurado con
revisores obligatorios en GitHub (detalle en el MD de despliegue).

## Configuración

El archivo `.env` está excluido del control de versiones mediante
`.gitignore` y no debe compartirse fuera de los canales seguros del
equipo.

| Variable | Descripción |
|---|---|
| `ENTORNO` | `desarrollo` o `produccion`. Controla la creación automática de tablas y la exposición de `/docs`. |
| `MYSQL_DATABASE_URL` | Cadena de conexión a la base propia (llaves de API y auditoría). |
| `MYSQL_TIMEOUT_SEGUNDOS` | Tiempo máximo de espera al conectar a MySQL (por defecto 10). |
| `PROSOFT_DATABASE_URL` | Cadena de conexión de solo lectura a Prosoft. |
| `PROSOFT_TIMEOUT_SEGUNDOS` | Tiempo máximo de espera al conectar o consultar Prosoft (por defecto 10). |
| `LLAVE_API_DIAS_EXPIRACION_MAXIMO` | Vigencia máxima de una llave, en días (por defecto 180). |
| `DIRECTORIO_LOGS` | Carpeta donde se escriben los logs de la aplicación, con rotación automática (por defecto `logs`). |
| `CORS_POLITICAS` | JSON con la política de CORS por prefijo de ruta. Vacío (`{}`) por defecto. Ver la sección [CORS](#cors). |
# zl-integration-api
