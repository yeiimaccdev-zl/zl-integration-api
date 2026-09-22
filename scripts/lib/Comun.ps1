<#
.SYNOPSIS
    Funciones compartidas por desplegar.ps1, rollback.ps1 e
    instalar_servicio_windows.ps1.

.DESCRIPTION
    Se cargan con dot-sourcing, nunca se ejecutan directamente:
        . "$PSScriptRoot\lib\Comun.ps1"
#>

$ErrorActionPreference = "Stop"

function Test-Salud {
    <#
    .SYNOPSIS
        Sondea GET /health hasta que responda 200 o se agote el tiempo.
    .OUTPUTS
        $true si respondió 200 dentro del tiempo dado; $false en cualquier
        otro caso (sin lanzar excepción — quien llama decide qué hacer).
    #>
    param(
        [string]$Url = "http://127.0.0.1:8000/health",
        [int]$TimeoutSegundos = 30,
        [int]$IntervaloSegundos = 2
    )

    $limite = (Get-Date).AddSeconds($TimeoutSegundos)
    while ((Get-Date) -lt $limite) {
        try {
            $respuesta = Invoke-WebRequest -Uri $Url -UseBasicParsing -TimeoutSec 5
            if ($respuesta.StatusCode -eq 200) {
                $cuerpo = $respuesta.Content | ConvertFrom-Json
                Write-Host "  /health -> 200 (mysql=$($cuerpo.mysql), prosoft=$($cuerpo.prosoft))"
                return $true
            }
            Write-Host "  /health -> HTTP $($respuesta.StatusCode), reintentando..."
        } catch {
            Write-Host "  /health no responde todavía ($($_.Exception.Message)), reintentando..."
        }
        Start-Sleep -Seconds $IntervaloSegundos
    }
    return $false
}

function Set-ReleaseActual {
    <#
    .SYNOPSIS
        Cambia el junction 'current' para que apunte a la release indicada.

    .DESCRIPTION
        Windows no ofrece un equivalente exacto al `mv -T` atómico de Linux
        para reemplazar un reparse point existente en una sola operación:
        se elimina el junction viejo (NUNCA la carpeta real de la release
        a la que apuntaba — eliminar un junction no borra su destino) y se
        crea uno nuevo. Hay una ventana de milisegundos entre ambos pasos,
        no una atomicidad perfecta; en la práctica no es perceptible porque
        el servicio de todas formas se reinicia justo después del swap.
    #>
    param(
        [Parameter(Mandatory = $true)][string]$RaizDespliegue,
        [Parameter(Mandatory = $true)][string]$RutaRelease
    )

    if (-not (Test-Path $RutaRelease)) {
        throw "La release '$RutaRelease' no existe; no se puede apuntar 'current' hacia ella."
    }

    $current = Join-Path $RaizDespliegue "current"

    if (Test-Path $current) {
        $item = Get-Item $current -Force
        if ($item.LinkType -ne "Junction") {
            throw "'$current' existe pero no es un junction (LinkType='$($item.LinkType)'). " +
                  "Revisar manualmente antes de continuar: un swap aquí podría borrar una carpeta real."
        }
        # Elimina solo el junction, no el contenido de la release a la que apuntaba.
        cmd /c rmdir "`"$current`"" | Out-Null
        if (Test-Path $current) {
            throw "No se pudo eliminar el junction 'current' existente."
        }
    }

    New-Item -ItemType Junction -Path $current -Target $RutaRelease | Out-Null
    Write-Host "  'current' ahora apunta a: $RutaRelease"
}

function Get-ReleaseActual {
    <#
    .SYNOPSIS
        Devuelve la ruta real (no el junction) a la que apunta 'current' hoy,
        o $null si 'current' todavía no existe (primer despliegue).
    #>
    param([Parameter(Mandatory = $true)][string]$RaizDespliegue)

    $current = Join-Path $RaizDespliegue "current"
    if (-not (Test-Path $current)) { return $null }
    return (Get-Item $current -Force).Target
}

function Get-ParametrosMySQLDesdeUrl {
    <#
    .SYNOPSIS
        Extrae usuario/contraseña/host/puerto/base de datos de una URL con
        el formato usado en MYSQL_DATABASE_URL: mysql+pymysql://user:pass@host:puerto/base

    .DESCRIPTION
        El separador entre credenciales y host es la ÚLTIMA '@' de la
        cadena, no la primera: si la contraseña real contiene un '@' sin
        codificar, tomar la primera ocurrencia partiría mal la URL. Se
        ancla host:puerto/base al final con una captura no-codiciosa para
        las credenciales, y dentro de las credenciales se separa usuario
        de contraseña por el PRIMER ':' (igual que RFC 3986 userinfo).
    #>
    param([Parameter(Mandatory = $true)][string]$Url)

    if ($Url -notmatch '^mysql\+pymysql://(?<credenciales>.+)@(?<vmhost>[^:@/]+):(?<puerto>\d+)/(?<basededatos>[^?\s]+)(?:\?.*)?$') {
        throw "MYSQL_DATABASE_URL no tiene el formato esperado 'mysql+pymysql://usuario:contrasena@host:puerto/basededatos'."
    }

    $partesCredenciales = $Matches.credenciales -split ':', 2
    if ($partesCredenciales.Count -ne 2) {
        throw "No se pudo separar usuario y contraseña en MYSQL_DATABASE_URL (falta ':' entre ambos)."
    }

    # Usuario/contraseña pueden venir percent-encoded (ej. '%40' por '@'),
    # que es la forma correcta de poner caracteres especiales en una URL.
    # UnescapeDataString es un no-op inofensivo si no hay nada codificado.
    return [PSCustomObject]@{
        Usuario     = [System.Uri]::UnescapeDataString($partesCredenciales[0])
        Contrasena  = [System.Uri]::UnescapeDataString($partesCredenciales[1])
        VmHost      = $Matches.vmhost
        Puerto      = $Matches.puerto
        BaseDeDatos = $Matches.basededatos
    }
}

function Invoke-BackupMySQL {
    <#
    .SYNOPSIS
        Genera un dump lógico verificado (tamaño > 0, contiene CREATE TABLE)
        con hash SHA-256, antes de aplicar cualquier migración. Requiere
        mysqldump.exe en el PATH (Cliente de línea de comandos de MySQL).

    .OUTPUTS
        Ruta al archivo .sql generado. Lanza excepción si algo falla o si
        el dump no pasa la verificación — quien llama debe detener el
        despliegue si esto lanza.
    #>
    param(
        [Parameter(Mandatory = $true)][string]$CarpetaBackups,
        [Parameter(Mandatory = $true)][string]$ArchivoEnv,
        # En el primer despliegue la base todavía no tiene tablas: no tiene
        # sentido exigir CREATE TABLE en un dump que legítimamente viene vacío.
        [bool]$ExigirEsquema = $true
    )

    if (-not (Get-Command mysqldump -ErrorAction SilentlyContinue)) {
        throw "mysqldump no está disponible en el PATH. Instalar el cliente de línea de comandos de MySQL " +
              "antes de desplegar (ver DESPLIEGUE_WINDOWS_SERVER_2022.md, sección de prerrequisitos)."
    }
    if (-not (Test-Path $ArchivoEnv)) {
        throw "No se encontró el archivo .env en '$ArchivoEnv'; no se puede hacer backup sin credenciales."
    }

    $lineaUrl = Get-Content $ArchivoEnv | Where-Object { $_ -match '^MYSQL_DATABASE_URL=' } | Select-Object -First 1
    if (-not $lineaUrl) {
        throw "MYSQL_DATABASE_URL no está definida en '$ArchivoEnv'."
    }
    $url = ($lineaUrl -split '=', 2)[1].Trim()
    $parametros = Get-ParametrosMySQLDesdeUrl -Url $url

    New-Item -ItemType Directory -Force -Path $CarpetaBackups | Out-Null
    $marcaDeTiempo = Get-Date -Format "yyyyMMdd_HHmmss"
    $archivoDump = Join-Path $CarpetaBackups "zl_integration_api_$marcaDeTiempo.sql"

    # La contraseña nunca se pasa en la línea de comandos (quedaría visible
    # en el listado de procesos): se usa un archivo de opciones temporal,
    # borrado en el 'finally' pase lo que pase.
    $archivoOpciones = [System.IO.Path]::GetTempFileName()
    @"
[client]
user=$($parametros.Usuario)
password=$($parametros.Contrasena)
host=$($parametros.VmHost)
port=$($parametros.Puerto)
"@ | Set-Content -Path $archivoOpciones -Encoding ascii

    try {
        & mysqldump "--defaults-extra-file=$archivoOpciones" --single-transaction --routines --triggers --events $parametros.BaseDeDatos |
            Out-File -FilePath $archivoDump -Encoding utf8
        if ($LASTEXITCODE -ne 0) {
            throw "mysqldump terminó con código $LASTEXITCODE."
        }
    } finally {
        Remove-Item $archivoOpciones -Force -ErrorAction SilentlyContinue
    }

    $tamano = (Get-Item $archivoDump).Length
    if ($tamano -eq 0) {
        throw "El dump '$archivoDump' quedó vacío; abortando despliegue."
    }
    if ($ExigirEsquema -and -not (Select-String -Path $archivoDump -Pattern "CREATE TABLE" -Quiet)) {
        throw "El dump '$archivoDump' no contiene 'CREATE TABLE'; probablemente está incompleto. Abortando."
    }

    $hash = Get-FileHash -Path $archivoDump -Algorithm SHA256
    "$($hash.Hash)  $(Split-Path $archivoDump -Leaf)" | Set-Content -Path "$archivoDump.sha256"

    Write-Host "  Backup verificado: $archivoDump ($([math]::Round($tamano / 1KB, 1)) KB, SHA-256 $($hash.Hash.Substring(0, 12))...)"
    return $archivoDump
}

function Remove-ReleasesAntiguas {
    <#
    .SYNOPSIS
        Conserva únicamente las N releases más recientes bajo releases\,
        sin tocar nunca la que 'current' señala en este momento.
    #>
    param(
        [Parameter(Mandatory = $true)][string]$RaizDespliegue,
        [int]$Conservar = 5
    )

    $releaseActual = Get-ReleaseActual -RaizDespliegue $RaizDespliegue
    $carpetaReleases = Join-Path $RaizDespliegue "releases"
    if (-not (Test-Path $carpetaReleases)) { return }

    $todas = Get-ChildItem $carpetaReleases -Directory | Sort-Object Name -Descending
    $aBorrar = $todas | Where-Object { $_.FullName -ne $releaseActual } | Select-Object -Skip ($Conservar - 1)

    foreach ($release in $aBorrar) {
        Write-Host "  Eliminando release antigua: $($release.FullName)"
        Remove-Item $release.FullName -Recurse -Force -ErrorAction SilentlyContinue
    }
}
