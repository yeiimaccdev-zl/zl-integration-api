<#
.SYNOPSIS
    Despliega un commit exacto de zl-integration-api en Windows Server, con
    rollback automático si el chequeo de salud posterior al swap falla.

.DESCRIPTION
    Pensado para ejecutarse tanto manualmente como desde el workflow de
    GitHub Actions (self-hosted runner). Sigue el mismo principio del resto
    del proyecto: fallar cerrado. Cualquier paso que lance una excepción
    detiene el despliegue ANTES de tocar 'current' — el servicio en
    producción sigue sirviendo la release anterior hasta que todo lo previo
    (venv, backup, migración, pruebas) haya pasado.

    Orden:
      1. Fetch + crear worktree inmutable del commit exacto en releases\.
      2. Copiar shared\.env dentro de la release (cada release queda
         autocontenida, incluida su config).
      3. Crear venv, instalar dependencias, 'pip check'.
      4. Backup de MySQL verificado (se omite el chequeo de CREATE TABLE
         únicamente en el primer despliegue, cuando la base aún no tiene
         tablas).
      5. Vista previa de la migración ('alembic upgrade head --sql', queda
         registrada en logs\) y luego aplicación real.
      6. Ejecutar la suite de pruebas DENTRO del venv de la release nueva,
         contra una base en memoria — no toca MySQL ni Prosoft reales. Si
         falla, se aborta ANTES de cualquier cambio visible para el tráfico.
      7. Swap de 'current' hacia la release nueva.
      8. Reiniciar el servicio NSSM y sondear /health.
      9. Si /health no responde 200 dentro del tiempo dado: ROLLBACK
         AUTOMÁTICO — 'current' vuelve a la release anterior, se reinicia
         el servicio otra vez, se re-verifica salud, y el script termina
         con código de error (el workflow de GitHub lo reporta como
         despliegue fallido). Esto es lo que da el "rollback en segundos":
         repuntar el junction y reiniciar NSSM no involucra reconstruir nada.
     10. Si todo salió bien: se conservan solo las últimas N releases.

.PARAMETER Commit
    SHA (completo o corto) o nombre de rama/tag a desplegar. Obligatorio:
    nunca se despliega "lo que haya en la rama" sin fijar un commit exacto.

.EXAMPLE
    .\desplegar.ps1 -Commit 6f2a9c1 -RepoUrl "https://github.com/zonalogistica-projects/zl-integration-api.git"

.EXAMPLE
    # Despliegues posteriores al primero, sin -RepoUrl (ya está clonado):
    .\desplegar.ps1 -Commit a1b2c3d
#>
param(
    [Parameter(Mandatory = $true)][string]$Commit,
    [string]$RaizDespliegue = "C:\zl-integration-api",
    [string]$RepoUrl,
    [string]$NombreServicio = "zl-integration-api",
    [string]$Puerto = "8000",
    [int]$ConservarReleases = 5,
    [int]$TimeoutSaludSegundos = 30
)

$ErrorActionPreference = "Stop"
. "$PSScriptRoot\lib\Comun.ps1"

$horaInicio = Get-Date
Write-Host "=== Despliegue de zl-integration-api - $horaInicio ===" -ForegroundColor Cyan
Write-Host "Commit solicitado: $Commit"

# --- 0. Validaciones previas ------------------------------------------------
$archivoEnvCompartido = Join-Path $RaizDespliegue "shared\.env"
if (-not (Test-Path $archivoEnvCompartido)) {
    throw "No existe $archivoEnvCompartido. Ejecutar antes .\configurar_estructura.ps1 y completar las credenciales reales."
}

$carpetaRepo = Join-Path $RaizDespliegue "repository"
if (-not (Test-Path $carpetaRepo)) {
    if (-not $RepoUrl) {
        throw "No existe '$carpetaRepo' todavia y no se indico -RepoUrl para clonarlo la primera vez."
    }
    Write-Host "[1/8] Clonando repositorio por primera vez..."
    git clone --no-checkout $RepoUrl $carpetaRepo
    if ($LASTEXITCODE -ne 0) { throw "git clone fallo." }
} else {
    Write-Host "[1/8] Repositorio ya existe, haciendo fetch..."
}
git -C $carpetaRepo fetch --prune origin
if ($LASTEXITCODE -ne 0) { throw "git fetch fallo." }

$shaCompleto = (git -C $carpetaRepo rev-parse $Commit).Trim()
if ($LASTEXITCODE -ne 0 -or -not $shaCompleto) {
    throw "El commit '$Commit' no se pudo resolver en el repositorio local. ¿Falta hacer fetch de esa rama?"
}
$shaCorto = $shaCompleto.Substring(0, 7)
Write-Host "  SHA completo: $shaCompleto"

$releaseAnteriorRuta = Get-ReleaseActual -RaizDespliegue $RaizDespliegue
$esPrimerDespliegue = ($null -eq $releaseAnteriorRuta)
if ($esPrimerDespliegue) {
    Write-Host "  Este es el PRIMER despliegue (todavia no hay una release activa)." -ForegroundColor Yellow
} else {
    Write-Host "  Release actual, para rollback si algo falla mas adelante: $releaseAnteriorRuta"
}

# --- 2. Crear release inmutable ---------------------------------------------
$marcaDeTiempo = Get-Date -Format "yyyyMMddHHmmss"
$nombreRelease = "$marcaDeTiempo-$shaCorto"
$rutaRelease = Join-Path $RaizDespliegue "releases\$nombreRelease"

Write-Host "[2/8] Creando release $nombreRelease ..."
git -C $carpetaRepo worktree add --detach $rutaRelease $shaCompleto | Out-Null
if ($LASTEXITCODE -ne 0) { throw "git worktree add fallo." }

foreach ($nombreSensible in @(".env", "zl_integration_api.db")) {
    if (Test-Path (Join-Path $rutaRelease $nombreSensible)) {
        throw "La release contiene '$nombreSensible', que no deberia estar versionado. Abortando por seguridad " +
              "antes de instalar nada. Revisar el repositorio."
    }
}

Copy-Item $archivoEnvCompartido (Join-Path $rutaRelease ".env")

# --- 3. Entorno virtual ------------------------------------------------------
Write-Host "[3/8] Creando entorno virtual e instalando dependencias..."
Push-Location $rutaRelease
try {
    python -m venv .venv
    if ($LASTEXITCODE -ne 0) { throw "No se pudo crear el entorno virtual con 'python -m venv .venv'." }

    & .\.venv\Scripts\python.exe -m pip install --upgrade pip --quiet
    & .\.venv\Scripts\pip.exe install . --quiet
    if ($LASTEXITCODE -ne 0) { throw "'pip install .' fallo dentro de la release nueva." }

    # Se instalan tambien las dependencias de desarrollo porque el paso 6
    # corre la suite de pruebas DENTRO de este mismo venv, antes del swap.
    & .\.venv\Scripts\pip.exe install ".[dev]" --quiet
    if ($LASTEXITCODE -ne 0) { throw "'pip install .[dev]' fallo (se necesita para correr las pruebas antes del swap)." }

    & .\.venv\Scripts\pip.exe check
    if ($LASTEXITCODE -ne 0) { throw "'pip check' encontro dependencias incompatibles en la release nueva." }
} finally {
    Pop-Location
}

# --- 4. Backup de MySQL -------------------------------------------------------
Write-Host "[4/8] Respaldando MySQL antes de migrar..."
$carpetaBackups = Join-Path $RaizDespliegue "shared\backups"
$rutaDump = Invoke-BackupMySQL -CarpetaBackups $carpetaBackups `
    -ArchivoEnv (Join-Path $rutaRelease ".env") `
    -ExigirEsquema (-not $esPrimerDespliegue)

# --- 5. Migracion: vista previa + aplicacion ----------------------------------
Write-Host "[5/8] Revisando y aplicando migraciones..."
$archivoLogMigracion = Join-Path $RaizDespliegue "logs\migracion_$marcaDeTiempo.sql"
Push-Location $rutaRelease
try {
    & .\.venv\Scripts\alembic.exe upgrade head --sql | Out-File -FilePath $archivoLogMigracion -Encoding utf8
    Write-Host "  Vista previa de la migracion guardada en $archivoLogMigracion"

    & .\.venv\Scripts\alembic.exe upgrade head
    if ($LASTEXITCODE -ne 0) {
        throw "'alembic upgrade head' fallo. La release NO se activo. MySQL puede haber quedado a mitad de " +
              "migracion -- revisar antes de reintentar; el respaldo esta en '$rutaDump' si hace falta restaurar."
    }
} finally {
    Pop-Location
}

# --- 6. Pruebas dentro de la release nueva, antes de exponerla ----------------
Write-Host "[6/8] Corriendo pruebas dentro de la release nueva (no toca MySQL ni Prosoft reales)..."
Push-Location $rutaRelease
try {
    & .\.venv\Scripts\python.exe -m pytest -q
    if ($LASTEXITCODE -ne 0) {
        throw "La suite de pruebas fallo en la release nueva. La release NO se activa. Ojo: el esquema de " +
              "MySQL ya se migro en el paso anterior -- si la migracion no es compatible hacia atras, la " +
              "release anterior podria fallar contra el nuevo esquema. Revisar antes de reintentar un despliegue."
    }
} finally {
    Pop-Location
}

# --- 7-9. Swap, reinicio, salud, rollback automatico si falla -----------------
Write-Host "[7/8] Activando la release nueva..."
Set-ReleaseActual -RaizDespliegue $RaizDespliegue -RutaRelease $rutaRelease

Write-Host "[8/8] Reiniciando el servicio y verificando salud..."
nssm restart $NombreServicio | Out-Null
Start-Sleep -Seconds 2

$saludOk = Test-Salud -Url "http://127.0.0.1:$Puerto/health" -TimeoutSegundos $TimeoutSaludSegundos

if (-not $saludOk) {
    Write-Host ""
    Write-Host "SALUD FALLO TRAS EL DESPLIEGUE -- INICIANDO ROLLBACK AUTOMATICO" -ForegroundColor Red

    if ($esPrimerDespliegue) {
        Write-Host "Es el primer despliegue: no hay una release anterior a la cual volver." -ForegroundColor Red
        Write-Host "Revisar logs\ y $archivoLogMigracion, y el estado del servicio manualmente." -ForegroundColor Red
        exit 1
    }

    Set-ReleaseActual -RaizDespliegue $RaizDespliegue -RutaRelease $releaseAnteriorRuta
    nssm restart $NombreServicio | Out-Null
    Start-Sleep -Seconds 2
    $saludTrasRollback = Test-Salud -Url "http://127.0.0.1:$Puerto/health" -TimeoutSegundos $TimeoutSaludSegundos

    if ($saludTrasRollback) {
        Write-Host "Rollback automatico completado: 'current' volvio a $releaseAnteriorRuta y el servicio responde." -ForegroundColor Yellow
    } else {
        Write-Host "El rollback automatico tampoco dejo el servicio saludable. Requiere intervencion manual inmediata." -ForegroundColor Red
        Write-Host "Ejecutar .\rollback.ps1 -Listar para ver releases disponibles, o revisar NSSM/MySQL/Prosoft directamente." -ForegroundColor Red
    }
    exit 1
}

Write-Host ""
Write-Host "Despliegue exitoso: $nombreRelease esta activa y saludable." -ForegroundColor Green
Remove-ReleasesAntiguas -RaizDespliegue $RaizDespliegue -Conservar $ConservarReleases

$duracion = (Get-Date) - $horaInicio
Write-Host "Duracion total: $([math]::Round($duracion.TotalSeconds, 1))s"
