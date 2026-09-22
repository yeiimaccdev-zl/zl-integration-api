<#
.SYNOPSIS
    Prepara la estructura de carpetas para desplegar zl-integration-api con
    releases inmutables y rollback rápido. Se ejecuta UNA SOLA VEZ, la
    primera vez que se configura el servidor.

.DESCRIPTION
    Requiere sesión de Administrador (crea carpetas fuera del perfil del
    usuario actual). No instala software ni toca IIS: solo arma el
    esqueleto de carpetas.

    Estructura resultante:
        C:\zl-integration-api\
        ├── releases\              (una subcarpeta inmutable por despliegue)
        ├── current                (junction -> releases\<release activa>, se crea en el primer despliegue)
        ├── shared\
        │   ├── .env                (credenciales reales, nunca se versiona ni se copia a git)
        │   └── backups\            (dumps de MySQL, uno por despliegue)
        └── logs\                  (logs de la aplicación y del servicio NSSM)

.EXAMPLE
    .\configurar_estructura.ps1 -RaizDespliegue "C:\zl-integration-api"
#>
param(
    [string]$RaizDespliegue = "C:\zl-integration-api"
)

$ErrorActionPreference = "Stop"

Write-Host "Creando estructura en $RaizDespliegue ..."

New-Item -ItemType Directory -Force -Path $RaizDespliegue | Out-Null
New-Item -ItemType Directory -Force -Path (Join-Path $RaizDespliegue "releases") | Out-Null
New-Item -ItemType Directory -Force -Path (Join-Path $RaizDespliegue "shared") | Out-Null
New-Item -ItemType Directory -Force -Path (Join-Path $RaizDespliegue "shared\backups") | Out-Null
New-Item -ItemType Directory -Force -Path (Join-Path $RaizDespliegue "logs") | Out-Null

$archivoEnv = Join-Path $RaizDespliegue "shared\.env"
if (-not (Test-Path $archivoEnv)) {
    Copy-Item ".env.example" $archivoEnv
    Write-Host "  Creado $archivoEnv a partir de .env.example — EDITARLO con las credenciales reales" -ForegroundColor Yellow
    Write-Host "  y dejar ENTORNO=produccion antes del primer despliegue." -ForegroundColor Yellow
} else {
    Write-Host "  $archivoEnv ya existe, no se sobrescribe."
}

Write-Host ""
Write-Host "Estructura lista. Pendiente antes del primer despliegue:" -ForegroundColor Cyan
Write-Host "  1. Editar $archivoEnv con las credenciales reales de MySQL y Prosoft."
Write-Host "  2. Confirmar ENTORNO=produccion en ese archivo."
Write-Host "  3. Ejecutar .\desplegar.ps1 -Commit <sha> para el primer despliegue."
