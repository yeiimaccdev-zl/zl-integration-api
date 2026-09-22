# Despliegue de `zl-integration-api` — Windows Server 2022 + IIS

> Procedimiento operativo completo: desde la VM vacía en Google Cloud hasta
> la API en producción, con despliegue automático desde GitHub y rollback
> en segundos si algo sale mal. Sin Docker, sin Cloud Run — todo corre
> directo sobre Windows Server 2022 e IIS, para evitar cobros por
> servicios administrados que no se están usando activamente.

Este documento reemplaza y amplía la guía de despliegue anterior: agrega
releases inmutables, backup y migración automatizados con verificación,
pruebas antes de exponer cada versión, rollback automático, y CI/CD con
GitHub Actions. El `README.MD` del proyecto no repite este contenido —
solo referencia esta guía y da los comandos del día a día.

## 0. Arquitectura objetivo

```
Internet / Sistemas internos (ZLHub, Power BI, SGA)
        |
        | HTTPS 443  (X-API-Key)
        v
   IIS (ARR + URL Rewrite) ── certificado TLS
        |
        | proxy interno 127.0.0.1:8000
        v
   Uvicorn + FastAPI  (servicio de Windows vía NSSM, cuenta de servicio dedicada)
        |                                  |
        | SQLAlchemy + pymysql             | SQLAlchemy + pymssql
        v                                  v
   MySQL propia                    SQL Server Prosoft (solo lectura, vía VPN)
   (llaves API + auditoría)

   GitHub Actions ──(runner self-hosted, saliente)──> ejecuta scripts\desplegar.ps1
   en la misma VM, sin abrir ningún puerto nuevo para desplegar.
```

Principios que definen todo lo que sigue:

- **El proceso Python nunca se expone directamente a Internet**: escucha
  solo en `127.0.0.1:8000`. IIS es el único punto de entrada externo.
- **Sin Docker, sin Cloud Run, sin ningún servicio de cómputo facturado
  por uso**: todo corre sobre la VM que ya existe, con software instalado
  directamente en Windows Server 2022. El único cargo variable relevante
  es la propia VM y su disco, no un servicio adicional.
- **`ENTORNO=produccion`** en `.env` es lo que apaga `/docs`, `/redoc` y la
  creación automática de tablas. Sin esto no es producción, aunque esté
  corriendo en el servidor real.
- **El esquema de base de datos se aplica solo con `alembic upgrade
  head`**, nunca automáticamente al iniciar el proceso.
- **Cada despliegue es una release inmutable**, no una modificación en
  sitio del código que ya está corriendo. Rollback significa apuntar a la
  carpeta anterior y reiniciar el servicio — segundos, no minutos, y sin
  reconstruir nada.
- **Nada se activa sin pasar antes por pruebas y por un backup
  verificado.** Si algo falla en cualquier paso previo al swap, la
  release en producción no se toca.

---

## 1. Responsabilidades

Dos perfiles de administrador distintos:

### 1.1 Administrador del proyecto de Google Cloud (IAM / Consola de GCP)

- [ ] Rol **Compute Admin** o equivalente sobre el proyecto.
- [ ] Permisos para editar **reglas de firewall de VPC**.
- [ ] Acceso para reservar una **IP externa estática** para la VM.
- [ ] Acceso al proveedor de DNS corporativo (el registro se administra
      desde cPanel, apuntando a la IP estática de la VM — igual que en el
      plan de ZLHub, cPanel nunca sirve archivos, solo resuelve el nombre).
- [ ] Confirmar que la VPN hacia Prosoft está asociada a esta VM/VPC y
      sigue activa.
- [ ] Si ZLHub también se despliega en esta misma VM más adelante:
      coordinar antes reglas de firewall y nombres de sitio en IIS para
      que no choquen entre sí (puertos internos distintos, bindings HTTPS
      distintos por `hostname`).

### 1.2 Administrador local del servidor Windows (RDP con sesión de Administrador)

- [ ] Instalar el rol **IIS** con **ARR** y **URL Rewrite**.
- [ ] Instalar **Python 3.12+**, **Git**, **NSSM** y el **cliente de línea
      de comandos de MySQL** (para `mysqldump`, usado en el backup
      automático antes de cada migración).
- [ ] Crear/editar **reglas de firewall de Windows**.
- [ ] Instalar el **certificado TLS** y enlazarlo en IIS.
- [ ] Registrar el **runner self-hosted de GitHub Actions** como servicio
      de Windows (sección 11).
- [ ] Acceso de red saliente hacia Prosoft (VPN) y hacia MySQL propio ya
      validado.

Varios pasos posteriores fallan silenciosamente si no se ejecutan con
sesión elevada — por ejemplo `nssm install` o instalar el rol de IIS sin
privilegios de administrador no avisan con un error claro, simplemente no
quedan bien configurados.

---

## 2. Preparar la VM en Google Cloud

**Quién ejecuta esto:** administrador de GCP.

1. Verificar que la VM Windows ya existente sea la que tiene la VPN hacia
   Prosoft activa — no crear una VM nueva sin esa VPN, es la razón de ser
   de toda la arquitectura.
2. Confirmar el tipo de máquina: `e2-medium` o `e2-standard-2` suele ser
   suficiente para arrancar; ajustar según el volumen real de
   consumidores (ZLHub, Power BI, SGA). Si ZLHub se suma a esta misma VM,
   revisar que el tamaño siga siendo suficiente para ambos procesos.
3. Reservar una **IP externa estática** para la VM (Consola → VPC network
   → IP addresses → Reserve static address). Sin esto, el DNS se rompe
   cada vez que la VM se reinicia.
4. Crear/verificar las reglas de firewall de VPC:
   - Entrante TCP **443** permitido, con target la etiqueta de red de
     esta VM.
   - Confirmar que **no existe** ninguna regla que exponga el **8000** al
     exterior.
   - Entrante **RDP (3389)** restringido solo a IPs de administración del
     equipo, nunca abierto a todo Internet.
5. Confirmar que el firewall de VPC permite la salida hacia Prosoft por
   la VPN y hacia el MySQL propio (puerto 3306) si vive en otra instancia.
6. Anotar la IP externa estática — se necesita para el DNS.
7. Definir una **política de snapshots** del disco de la VM (diaria,
   retenida algunos días) desde Compute Engine → Snapshots o Snapshot
   schedules — es la red de seguridad ante un problema que ni el rollback
   de aplicación ni el backup de MySQL cubren (ej. el propio SO
   corrupto).

---

## 3. Configurar el DNS

**Quién ejecuta esto:** administrador de GCP / DNS corporativo (cPanel).

1. Crear un registro `A` para el nombre definido (ej.
   `api-colaboradores.zonalogistica.com.co`) apuntando a la IP externa
   estática de la VM.
2. Esperar la propagación.
3. Validar con `nslookup api-colaboradores.zonalogistica.com.co` desde
   una máquina externa a la VM **antes** de continuar con el certificado
   TLS — un certificado emitido contra un DNS que no resuelve genera
   problemas de validación.

> **No avanzar a la sección 9 (salida real a producción) sin haber
> completado y verificado primero las secciones 4 a 8.** Cambiar el DNS
> antes de tener IIS, el certificado y el servicio funcionando deja el
> dominio apuntando a algo que no responde.

---

## 4. Preparar el servidor Windows

**Quién ejecuta esto:** administrador local, sesión de Administrador.

### 4.1 Rol IIS con ARR y URL Rewrite

1. **Administrador del servidor** → **Agregar roles y características**.
2. Rol **Servidor web (IIS)**, con al menos: contenido estático,
   documento predeterminado, filtrado de solicitudes, registro en formato
   W3C.
3. Instalar **Application Request Routing (ARR)** y **URL Rewrite**
   (ninguno viene con el rol por defecto).
4. Reiniciar si el instalador lo pide.

### 4.2 Python

1. Instalar Python 3.12 o superior, 64 bits, desde python.org.
2. Marcar **"Add python.exe to PATH"** durante la instalación.
3. Verificar en una consola nueva:
   ```powershell
   python --version
   pip --version
   ```

### 4.3 Git

1. Instalar [Git para Windows](https://git-scm.com/download/win).
2. Verificar:
   ```powershell
   git --version
   ```
   Es un prerrequisito nuevo respecto al despliegue anterior: ahora cada
   despliegue crea una release con `git worktree`, no solo un `git pull`
   ocasional.

### 4.4 NSSM

1. Descargar NSSM desde [nssm.cc](https://nssm.cc/).
2. Copiar `nssm.exe` (64 bits) a `C:\tools\nssm\`.
3. Agregar esa carpeta al `PATH` del sistema.
4. Verificar:
   ```powershell
   nssm version
   ```

### 4.5 Cliente de línea de comandos de MySQL (nuevo)

Necesario para que `scripts\desplegar.ps1` pueda respaldar la base antes
de cada migración con `mysqldump`.

1. Descargar **"MySQL Command Line Client"** o el instalador completo de
   **MySQL Installer for Windows**, seleccionando únicamente el
   componente de cliente — **no** instalar un servidor MySQL en esta VM.
2. Agregar la carpeta `bin` de la instalación (contiene `mysqldump.exe`)
   al `PATH` del sistema.
3. Verificar:
   ```powershell
   mysqldump --version
   ```

### 4.6 Clonar el repositorio y preparar la estructura

```powershell
git clone <url-del-repositorio> C:\zl-integration-api\repository
cd C:\zl-integration-api\repository
.\scripts\configurar_estructura.ps1 -RaizDespliegue "C:\zl-integration-api"
```

Este script crea `C:\zl-integration-api\{releases, shared, shared\backups,
logs}` y copia `.env.example` a `shared\.env`. A diferencia de una
preparación desechable, este clon en `C:\zl-integration-api\repository`
**se conserva** — es el mismo clon técnico que después usan
`instalar_servicio_windows.ps1` (sección 5.2), `desplegar.ps1` (sección
5.3 en adelante) y `rollback.ps1` (sección 13.2): los tres se ejecutan con
`cd C:\zl-integration-api\repository` primero, así que esa carpeta debe
existir *antes* de llegar a la sección 5. `desplegar.ps1` detecta que
`repository\` ya existe y hace `git fetch` en vez de clonar de nuevo, así
que seguir pasándole `-RepoUrl` en el primer despliegue (sección 5.3) no
hace nada — es inofensivo dejarlo por costumbre, pero ya no es
obligatorio en ningún punto del procedimiento.


```powershell
cd C:\zl-integration-api\repository
.\scripts\instalar_servicio.ps1
```

---

## 5. Configurar credenciales y registrar el servicio

**Quién ejecuta esto:** administrador local.

### 5.1 Completar `shared\.env`

```powershell
notepad C:\zl-integration-api\shared\.env
```

Completar como mínimo:

```
ENTORNO=produccion
MYSQL_DATABASE_URL=mysql+pymysql://usuario:contrasena@host:3306/nombre_base
MYSQL_TIMEOUT_SEGUNDOS=10
PROSOFT_DATABASE_URL=mssql+pymssql://usuario:contrasena@host:1433/nombre_base
PROSOFT_TIMEOUT_SEGUNDOS=10
DIRECTORIO_LOGS=logs
```

Puntos críticos:

- `ENTORNO=produccion` es obligatorio.
- El usuario de `PROSOFT_DATABASE_URL` debe ser de **solo lectura**.
- Si la contraseña de MySQL o Prosoft tiene caracteres especiales
  (`@`, `:`, `/`, `%`), debe ir codificada como URL (ej. `@` → `%40`) —
  es un requisito del formato de `MYSQL_DATABASE_URL`/`PROSOFT_DATABASE_URL`
  en sí, no solo de los scripts de despliegue.
- Este archivo **nunca** se versiona ni se copia fuera del gestor de
  credenciales del equipo. Cada release nueva recibe una copia propia
  (`scripts\desplegar.ps1` la hace automáticamente) — editar solo este
  archivo en `shared\`, nunca el `.env` dentro de una release ya creada.

### 5.2 Registrar el servicio de Windows

```powershell
cd C:\zl-integration-api\repository
.\scripts\instalar_servicio_windows.ps1 -RaizDespliegue "C:\zl-integration-api"
```

Es normal que este paso avise que `current` todavía no existe — el
servicio queda registrado apuntando ahí, pero no podrá iniciar hasta el
primer despliegue (sección 5.3). Este script:

- Registra el servicio escuchando en **`127.0.0.1:8000`** (no
  `0.0.0.0`): el proceso mismo rechaza conexiones que no vengan de la
  propia máquina, como segunda capa de protección independiente del
  firewall.
- Lo corre bajo la cuenta de servicio virtual `NT SERVICE\zl-integration-api`,
  sin privilegios de administrador y sin contraseña que gestionar — no
  `LocalSystem`.
- Ajusta permisos para que esa cuenta solo pueda escribir en `logs\` y
  `shared\backups\`; el resto queda de solo lectura para ella.
- Configura arranque automático y reinicio automático si el proceso cae.

### 5.3 Primer despliegue

```powershell
cd C:\zl-integration-api\repository
.\scripts\desplegar.ps1 -Commit <sha-o-rama> -RepoUrl "https://github.com/<org>/zl-integration-api.git"
```

Qué hace, en orden (ver también la cabecera del propio script):

1. Clona/actualiza el repositorio técnico en `repository\`.
2. Crea `releases\<fecha>-<sha>\` con `git worktree`.
3. Copia `shared\.env` dentro de la release.
4. Crea el entorno virtual e instala dependencias (`pip install .` y
   `pip install ".[dev]"`, esta última porque el paso 6 corre las pruebas
   dentro de la release antes de exponerla).
5. Respalda MySQL con `mysqldump`, verifica que el dump no esté vacío
   (y que contenga `CREATE TABLE`, salvo en este primer despliegue, donde
   la base todavía no tiene tablas) y guarda un hash SHA-256 junto al
   archivo.
6. Aplica las migraciones (`alembic upgrade head`, con una vista previa
   en SQL guardada en `logs\` antes de aplicarlas de verdad).
7. Corre la suite de pruebas dentro del propio venv de la release nueva.
8. Solo si todo lo anterior pasó: cambia `current` hacia la release
   nueva, reinicia el servicio y verifica `/health`.
9. Si `/health` no responde bien y esto **no** es el primer despliegue,
   revierte automáticamente — en el primer despliegue no hay a dónde
   volver, así que si esto falla aquí, revisar manualmente (ver sección
   13.3).

### 5.4 Generar las API Keys de los sistemas consumidores

Se ejecuta **dentro** del entorno virtual de la release activa:

```powershell
cd C:\zl-integration-api\current
.\.venv\Scripts\python.exe scripts\seed_api_keys.py
```

- Cada llave se imprime **una sola vez** en texto plano — cópiala de
  inmediato al gestor de credenciales del equipo.
- Una llave distinta por sistema consumidor (ZLHub, Power BI, SGA, etc.),
  cada una con el alcance que le corresponda.
- Si una llave se filtra o vence (máximo 180 días,
  `LLAVE_API_DIAS_EXPIRACION_MAXIMO`):
  ```powershell
  .\.venv\Scripts\python.exe scripts\rotar_llave.py <sistema>
  ```

### 5.5 Verificación manual

```powershell
curl http://127.0.0.1:8000/health
```

Debe responder `200` con `{"status":"ok","mysql":"arriba","prosoft":"arriba"}`.

---

## 6. Configurar IIS como proxy reverso

**Quién ejecuta esto:** administrador local.

### 6.1 Habilitar el proxy en ARR

1. IIS Manager → nodo del servidor (nivel raíz, no un sitio) →
   **Application Request Routing Cache** → **Server Proxy Settings** →
   marcar **Enable proxy** → Aplicar.

### 6.2 Crear el sitio en IIS

1. Crear un sitio enlazado al dominio `api-colaboradores.zonalogistica.com.co`.
2. Asociar el certificado TLS (sección 7) en el binding HTTPS (443).
3. No hace falta apuntar la carpeta física del sitio a nada del proyecto
   Python: IIS solo reenvía tráfico.

### 6.3 Regla de reenvío (URL Rewrite → Reverse Proxy)

1. Sitio → **URL Rewrite** → **Add Rule(s)** → **Reverse Proxy**.
2. Servidor destino: `127.0.0.1:8000`.
3. Marcar **Enable SSL Offloading** (HTTPS afuera, HTTP hacia Uvicorn en
   loopback).
4. Guardar — genera una regla en el `web.config` del sitio.

### 6.4 Reenvío correcto de la IP de origen

Para que `ip_origen` en la tabla de auditoría sea confiable (el
middleware de la app confía en `X-Forwarded-For`), IIS/ARR debe
**sobrescribir** ese encabezado en cada solicitud entrante, no anexarlo.
Confirmar con el equipo de TI cómo queda configurado exactamente antes de
tratar ese campo como prueba definitiva de origen en una auditoría.

---

## 7. Certificado TLS

**Quién ejecuta esto:** administrador local.

1. Obtener el certificado para `api-colaboradores.zonalogistica.com.co`
   de la autoridad certificadora corporativa.
2. Importarlo al almacén de certificados de la máquina: **certlm.msc** →
   **Personal** → **Certificados** → **Todas las tareas** → **Importar**,
   incluyendo la clave privada.
3. IIS Manager → sitio → **Bindings** → editar/crear el binding
   **https/443** → seleccionar el certificado.
4. Verificar la fecha de expiración y dejar un recordatorio de renovación
   — un certificado vencido tumba el acceso externo aunque la API interna
   siga funcionando.

> **Alternativa a evaluar más adelante:** si la organización prefiere
> renovación automática en vez de manual, [win-acme](https://www.win-acme.com/)
> es el equivalente en Windows de Certbot (usado en el plan de ZLHub) y
> puede programarse como tarea programada. No es parte de este
> procedimiento porque el proceso actual usa la CA corporativa, no Let's
> Encrypt — queda como mejora futura, no como bloqueante.

---

## 8. Cerrar el acceso público al 8000 y firewall de Windows

**Quién ejecuta esto:** administrador local.

1. **Firewall de Windows Defender con seguridad avanzada.**
2. Confirmar/crear regla de entrada permitiendo **TCP 443**.
3. Confirmar que **no existe** ninguna regla de entrada permitiendo
   **TCP 8000** desde perfiles públicos o de dominio. Con el servicio ya
   escuchando en `127.0.0.1` (sección 5.2), esto es una segunda capa, no
   la única defensa.
4. Revisar también el firewall de VPC de GCP (sección 2) para confirmar
   que tampoco hay ahí una regla abriendo el 8000.

---

## 9. Validación completa en producción

**Antes de este punto, la sección 3 (DNS) debe estar resuelta y
verificada.**

Desde una máquina **fuera** de la VM:

- [ ] `https://api-colaboradores.zonalogistica.com.co/health` responde
      `200` con `mysql: arriba` y `prosoft: arriba`.
- [ ] La conexión usa HTTPS válido, sin advertencias de certificado.
- [ ] Un endpoint real (`/api/v1/integraciones/colaboradores/{cedula}`)
      responde correctamente con una API Key de pruebas válida.
- [ ] Una solicitud **sin** `X-API-Key` es rechazada (`401`/`403`).
- [ ] `/docs` responde `404` desde fuera (confirma `ENTORNO=produccion`).

## 10. Prueba paralela contra el sistema anterior (opcional, recomendado para consumidores críticos)

Antes de migrar un consumidor crítico (ej. Power BI en un reporte que ya
está en producción con otra fuente):

1. Tomar una muestra de colaboradores activos e inactivos.
2. Consultar la misma persona en el sistema anterior y en
   `zl-integration-api`.
3. Comparar cédula, correo, cargo, sede, estado, centro de costos y demás
   campos relevantes.
4. Documentar cualquier diferencia — Prosoft/Nómina es la fuente válida
   para la operación nueva.
5. No migrar un consumidor crítico hasta entender las diferencias
   encontradas.

---

## 11. CI/CD con GitHub Actions

Con esto, un `push` a `main` (tras pasar pruebas y, si se configura,
aprobación manual) despliega solo, sin que alguien tenga que conectarse
por RDP a ejecutar `desplegar.ps1` a mano. El workflow ya está en el
repositorio: `.github/workflows/despliegue.yml`.

### 11.1 Instalar el runner self-hosted en la VM

**Por qué self-hosted y no SSH/WinRM desde GitHub hacia la VM:** un
runner self-hosted se conecta **hacia afuera** (hacia GitHub), igual que
cualquier otro proceso saliente de la VM. No hace falta abrir ningún
puerto entrante nuevo ni gestionar llaves SSH — es la opción que menos
superficie de ataque agrega, coherente con el resto de este documento.

1. En GitHub: repositorio → **Settings** → **Actions** → **Runners** →
   **New self-hosted runner** → sistema operativo **Windows**.
2. Seguir las instrucciones que GitHub genera ahí (incluyen un token de
   registro de un solo uso). En resumen, desde una PowerShell de
   Administrador en la VM:
   ```powershell
   mkdir C:\actions-runner ; cd C:\actions-runner
   Invoke-WebRequest -Uri <url-que-da-github> -OutFile actions-runner.zip
   Expand-Archive -Path actions-runner.zip -DestinationPath .
   .\config.cmd --url https://github.com/<org>/zl-integration-api --token <token-de-github> --labels windows,zl-integration-api
   ```
3. Instalarlo como servicio de Windows (para que sobreviva reinicios,
   igual que el resto de servicios de este documento) — el propio
   `config.cmd` ofrece la opción de correr como servicio durante la
   configuración interactiva; aceptar esa opción para que quede
   registrado en **Servicios de Windows** como cualquier otro.
4. Confirmar en GitHub → Settings → Actions → Runners que aparece **Idle**
   (en línea, esperando trabajo).

Las etiquetas `windows` y `zl-integration-api` del paso 2 son las mismas
que usa `runs-on: [self-hosted, windows, zl-integration-api]` en el
workflow — así, si ZLHub más adelante registra su propio runner en esta
misma VM con otras etiquetas, cada workflow solo dispara el suyo.

### 11.2 Ambiente `produccion` con aprobación manual (recomendado)

1. Repositorio → **Settings** → **Environments** → **New environment** →
   nombre exacto `produccion` (debe coincidir con `environment:
   produccion` del workflow).
2. **Required reviewers**: agregar a quien deba aprobar cada despliegue
   antes de que corra. Con esto, cada `push` a `main` queda **pausado**
   hasta que alguien de la lista lo apruebe desde la pestaña **Actions**
   del repositorio — el pipeline no se ejecuta solo por hacer push.
3. Sin este paso, el workflow igual funciona, pero despliega
   automáticamente en cuanto las pruebas pasan, sin pausa para revisión
   humana.

### 11.3 Verificar el pipeline

1. Hacer un cambio trivial (ej. un comentario) en una rama, abrir un pull
   request hacia `main` — confirmar que el job **pruebas** corre solo.
2. Al hacer merge a `main`, confirmar que el job **desplegar** queda
   esperando aprobación (si se configuró el paso 11.2) y que, al
   aprobarlo, ejecuta `scripts\desplegar.ps1` en la VM.
3. Revisar el log del job en GitHub — debe verse la misma salida que al
   correr `desplegar.ps1` manualmente (sección 5.3).

### 11.4 Qué sigue siendo manual

El pipeline no reemplaza el primer despliegue (sección 5, que ya deja
`repository\` y `current` creados) ni el registro del servicio (sección
5.2) — esos son de una sola vez. Tampoco reemplaza el simulacro de
rollback (sección 13.4), que conviene ejecutar a mano al menos una vez.

---

## 12. Desplegar una nueva versión

Dos caminos, mismo mecanismo por debajo:

**Automático (recomendado, una vez configurada la sección 11):** hacer
merge a `main`. El pipeline corre pruebas, y si pasan (y si hay
aprobación manual configurada, tras aprobarla), despliega solo.

**Manual:**
```powershell
cd C:\zl-integration-api\repository
.\scripts\desplegar.ps1 -Commit <sha>
```
(`-RepoUrl` es opcional en todo el procedimiento — `repository\` ya quedó
clonado en la sección 4.6. El parámetro solo importa si `repository\` no
existiera por algún motivo, por ejemplo al reconstruir el servidor desde
cero).

En ambos casos, si algo fallara **después** de que el swap ya se hizo, el
propio script revierte solo (sección 13.1) — no hace falta ni un `nssm
stop` manual como en el procedimiento anterior de este proyecto.

---

## 13. Rollback

### 13.1 Rollback automático (lo hace `desplegar.ps1` solo)

Si `/health` no responde `200` dentro del tiempo dado justo después de
activar una release nueva, el script:

1. Vuelve a apuntar `current` hacia la release anterior.
2. Reinicia el servicio.
3. Vuelve a verificar `/health`.
4. Termina con código de error — en el pipeline de GitHub, ese job queda
   marcado como fallido, visible para todo el equipo.

Esto toma segundos porque no reconstruye nada: la release anterior sigue
intacta en disco, con su propio `.venv` ya instalado — repuntar el
junction y reiniciar NSSM es todo lo que hace falta.

### 13.2 Rollback manual (`rollback.ps1`)

Para cuando el problema se nota **después** del despliegue (el
automático de 13.1 solo actúa en el momento mismo del swap):

```powershell
cd C:\zl-integration-api\repository
.\scripts\rollback.ps1 -Listar                 # ver releases disponibles y cuál está activa
.\scripts\rollback.ps1                         # volver a la inmediatamente anterior
.\scripts\rollback.ps1 -Release <nombre-exacto> # volver a una release específica
```

### 13.3 Advertencia sobre migraciones

**Ni el rollback automático ni el manual revierten migraciones de base de
datos.** Si la release que se está abandonando aplicó una migración de
esquema, volver el código atrás puede dejarlo corriendo contra un
esquema que ya no reconoce. Antes de un rollback después de una
migración:

1. Revisar la vista previa SQL guardada en `logs\migracion_<fecha>.sql`
   de ese despliegue — indica exactamente qué cambió el esquema.
2. Si el cambio es aditivo y compatible hacia atrás (agregar una columna
   opcional, por ejemplo), el rollback de código es seguro.
3. Si no lo es, restaurar también el backup de MySQL correspondiente
   (`shared\backups\`, con su archivo `.sha256` para confirmar
   integridad) es parte del rollback, no un paso aparte — coordinar esto
   con quien tenga acceso de administrador a la base antes de proceder.

### 13.4 Simulacro de rollback (obligatorio antes de cerrar la Fase 1)

No dar por completo el despliegue sin haber probado el rollback al menos
una vez, en una ventana controlada:

1. Desplegar una release cualquiera (puede ser un cambio trivial).
2. Ejecutar `.\scripts\rollback.ps1` y confirmar que el servicio vuelve a
   responder `/health` correctamente con la release anterior activa.
3. Medir cuánto tardó de punta a punta — debe ser cuestión de segundos,
   no minutos. Si toma más, algo en el entorno (antivirus interceptando
   el `Rename-Item`, disco lento, NSSM tardando en reiniciar) merece
   revisión antes de confiar en el mecanismo para un incidente real.

---

## 14. Monitoreo continuo post-despliegue

Como mínimo, dejar vigilado (manual o con una herramienta externa
apuntando a `/health` y a los logs):

- Disponibilidad de la API (`/health`).
- Estado de la VPN con Prosoft.
- Disponibilidad de MySQL propio.
- Tiempo promedio de respuesta.
- Tasa de errores por hora/día (`logs\zl-integration-api.log`, formato
  JSON, y `logs\servicio-stderr.log` del servicio NSSM).
- Consumidores activos y consultas lentas (tabla de auditoría
  `auditoria_solicitudes`).
- Intentos de acceso no autorizado (categoría `AUTENTICACION`/
  `AUTORIZACION` en la auditoría).
- Que el runner self-hosted de GitHub Actions siga **Idle** en
  Settings → Actions → Runners — si aparece desconectado, los próximos
  `push` a `main` no van a poder desplegar solos.

---

## 15. Referencia rápida

| Acción | Comando |
|---|---|
| Desplegar (manual) | `.\scripts\desplegar.ps1 -Commit <sha>` |
| Rollback a la anterior | `.\scripts\rollback.ps1` |
| Rollback a una release específica | `.\scripts\rollback.ps1 -Release <nombre>` |
| Ver releases disponibles | `.\scripts\rollback.ps1 -Listar` |
| Ver estado del servicio | `nssm status zl-integration-api` |
| Detener / iniciar / reiniciar | `nssm stop`/`start`/`restart zl-integration-api` |
| Editar configuración del servicio (GUI) | `nssm edit zl-integration-api` |
| Ver qué release está activa | `(Get-Item C:\zl-integration-api\current).Target` |
| Rotar una API Key | `current\.venv\Scripts\python.exe scripts\rotar_llave.py <sistema>` |

---

## 16. Checklist final de cierre

- [ ] Diagrama de arquitectura entregado (sección 0).
- [ ] URL de producción documentada.
- [ ] Endpoints disponibles y alcances requeridos (tabla del `README.MD`).
- [ ] Estructura de releases y ubicación de `shared\.env` documentada
      (sección 4.6).
- [ ] Procedimiento para generar/rotar una API Key (sección 5.4).
- [ ] Procedimiento de despliegue, manual y automático (secciones 5.3 y
      12).
- [ ] **Rollback probado al menos una vez, con tiempo medido** (sección
      13.4) — no solo documentado, ejecutado.
- [ ] Runner self-hosted registrado y en estado **Idle**; ambiente
      `produccion` con revisores configurados si aplica (sección 11).
- [ ] Ubicación de logs documentada (`logs\zl-integration-api.log`,
      `logs\servicio-stdout.log`, `logs\servicio-stderr.log`,
      `logs\migracion_<fecha>.sql`).
- [ ] Procedimiento para comprobar VPN y SQL Server (`/health`).
- [ ] Plan de acción si Prosoft no responde (`/health` marca `prosoft:
      no_disponible`; revisar primero el estado de la VPN antes de
      asumir que el servicio de Prosoft cayó).
- [ ] Política de snapshots del disco de la VM configurada (sección 2,
      paso 7).
