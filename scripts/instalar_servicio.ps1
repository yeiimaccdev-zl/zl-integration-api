<#
.SYNOPSIS
    Instala y configura el servicio de Windows (NSSM) para zl-integration-api.
    Se ejecuta UNA SOLA VEZ, después de configurar_estructura.ps1 y antes del
    primer .\desplegar.ps1.
#>
param(
    [string]$RaizDespliegue = "C:\zl-integration-api",
    [string]$NombreServicio = "zl-integration-api",
    [string]$Puerto = "8000"
)

$ErrorActionPreference = "Stop"

$pythonRelease = Join-Path $RaizDespliegue "current\.venv\Scripts\python.exe"
$directorioApp  = Join-Path $RaizDespliegue "current"
$carpetaLogs    = Join-Path $RaizDespliegue "logs"

nssm install $NombreServicio $pythonRelease
nssm set $NombreServicio AppDirectory $directorioApp
nssm set $NombreServicio AppParameters "-m uvicorn app.main:app --host 127.0.0.1 --port $Puerto"
nssm set $NombreServicio AppStdout (Join-Path $carpetaLogs "stdout.log")
nssm set $NombreServicio AppStderr (Join-Path $carpetaLogs "stderr.log")
nssm set $NombreServicio AppRotateFiles 1
nssm set $NombreServicio AppRotateBytes 10485760

Write-Host "Servicio '$NombreServicio' instalado. Pendiente: correr el primer .\desplegar.ps1 -Commit <sha> -RepoUrl <url>."