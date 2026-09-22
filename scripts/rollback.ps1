<#
.SYNOPSIS
    Vuelve manualmente a una release anterior, sin pasar por el pipeline de
    despliegue. Para cuando un problema se nota horas o dias despues del
    despliegue automatico (el rollback automatico de desplegar.ps1 solo
    actua en el momento mismo del swap).

.DESCRIPTION
    NO revierte migraciones de base de datos. Si la release nueva aplico
    una migracion no compatible hacia atras, volver el codigo a la version
    anterior puede dejarla funcionando contra un esquema que no reconoce.
    Evaluar esquema/datos ANTES de decidir un rollback cuando hubo
    migraciones de por medio (ver DESPLIEGUE_WINDOWS_SERVER_2022.md).

.EXAMPLE
    # Ver que releases hay disponibles y cual esta activa:
    .\rollback.ps1 -Listar

.EXAMPLE
    # Volver a la release inmediatamente anterior a la activa:
    .\rollback.ps1

.EXAMPLE
    # Volver a una release especifica:
    .\rollback.ps1 -Release "20260920140501-a1b2c3d"
#>
param(
    [string]$RaizDespliegue = "C:\zl-integration-api",
    [string]$NombreServicio = "zl-integration-api",
    [string]$Puerto = "8000",
    [string]$Release,
    [switch]$Listar,
    [int]$TimeoutSaludSegundos = 30
)

$ErrorActionPreference = "Stop"
. "$PSScriptRoot\lib\Comun.ps1"

$carpetaReleases = Join-Path $RaizDespliegue "releases"
$releaseActualRuta = Get-ReleaseActual -RaizDespliegue $RaizDespliegue
$todas = Get-ChildItem $carpetaReleases -Directory | Sort-Object Name -Descending

if ($Listar) {
    Write-Host "Releases disponibles (mas reciente primero):"
    foreach ($r in $todas) {
        $marca = if ($r.FullName -eq $releaseActualRuta) { " <- ACTIVA" } else { "" }
        Write-Host "  $($r.Name)$marca"
    }
    exit 0
}

if ($Release) {
    $destino = $todas | Where-Object { $_.Name -eq $Release }
    if (-not $destino) {
        throw "No se encontro la release '$Release' bajo '$carpetaReleases'. Usar -Listar para ver las disponibles."
    }
    $rutaDestino = $destino.FullName
} else {
    # Sin -Release: la inmediatamente anterior a la activa en la lista ordenada.
    $indiceActual = [array]::IndexOf($todas.FullName, $releaseActualRuta)
    if ($indiceActual -lt 0 -or ($indiceActual + 1) -ge $todas.Count) {
        throw "No hay una release anterior identificable automaticamente. Usar -Listar y -Release <nombre> explicito."
    }
    $rutaDestino = $todas[$indiceActual + 1].FullName
}

if ($rutaDestino -eq $releaseActualRuta) {
    Write-Host "La release destino ya es la activa ($rutaDestino). Nada que hacer." -ForegroundColor Yellow
    exit 0
}

Write-Host "Rollback: $releaseActualRuta -> $rutaDestino" -ForegroundColor Cyan
Write-Host "Recordatorio: esto NO revierte migraciones de base de datos. Confirmar compatibilidad de esquema" -ForegroundColor Yellow
Write-Host "antes de continuar si el despliegue que se esta revirtiendo aplico una migracion." -ForegroundColor Yellow

Set-ReleaseActual -RaizDespliegue $RaizDespliegue -RutaRelease $rutaDestino
nssm restart $NombreServicio | Out-Null
Start-Sleep -Seconds 2

$saludOk = Test-Salud -Url "http://127.0.0.1:$Puerto/health" -TimeoutSegundos $TimeoutSaludSegundos
if ($saludOk) {
    Write-Host "Rollback completado, el servicio responde." -ForegroundColor Green
} else {
    Write-Host "Rollback aplicado pero /health no respondio a tiempo. Revisar logs\ y 'nssm status $NombreServicio'." -ForegroundColor Red
    exit 1
}
