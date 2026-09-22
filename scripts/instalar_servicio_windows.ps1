<#
.SYNOPSIS
    Registra zl-integration-api como servicio de Windows usando NSSM,
    apuntando permanentemente a la release activa (el junction 'current').

.DESCRIPTION
    Requiere permisos de administrador y que NSSM ya este instalado y
    disponible en el PATH. Se ejecuta UNA SOLA VEZ por servidor: como el
    ExecStart apunta a 'current\.venv\Scripts\python.exe' (no a una release
    especifica), desplegar.ps1 puede cambiar que release esta activa sin
    tener que volver a registrar el servicio en cada despliegue.

    Dos correcciones respecto a una configuracion NSSM por defecto:
    - Escucha SOLO en 127.0.0.1, nunca en 0.0.0.0. Que el proceso mismo no
      pueda aceptar conexiones externas es una segunda capa de proteccion
      independiente de que el firewall este bien configurado.
    - Corre bajo una cuenta de servicio virtual dedicada
      ("NT SERVICE\<NombreServicio>"), no como LocalSystem (que tiene
      privilegios de administrador completos en la maquina). Windows crea
      esta cuenta automaticamente al asociarla a un servicio, sin
      necesidad de definir ni guardar una contrasena.

.EXAMPLE
    .\instalar_servicio_windows.ps1 -RaizDespliegue "C:\zl-integration-api"
#>
param(
    [string]$RaizDespliegue = "C:\zl-integration-api",
    [string]$NombreServicio = "zl-integration-api",
    [string]$Puerto = "8000"
)

$ErrorActionPreference = "Stop"

$rutaPython = Join-Path $RaizDespliegue "current\.venv\Scripts\python.exe"
$rutaLogs = Join-Path $RaizDespliegue "logs"
$rutaCurrent = Join-Path $RaizDespliegue "current"

New-Item -ItemType Directory -Force -Path $rutaLogs | Out-Null

if (-not (Test-Path $rutaCurrent)) {
    Write-Host "Aviso: '$rutaCurrent' todavia no existe (normal si este es el primer despliegue)." -ForegroundColor Yellow
    Write-Host "El servicio queda registrado, pero no podra iniciar hasta el primer '.\desplegar.ps1'." -ForegroundColor Yellow
}

# NOTA: se apunta a 'current\...' como cadena de texto -- NSSM no resuelve
# el junction al registrar, lo resuelve cada vez que el proceso arranca.
# Por eso desplegar.ps1 no necesita volver a llamar a este script.
nssm install $NombreServicio $rutaPython "-m uvicorn app.main:app --host 127.0.0.1 --port $Puerto"
nssm set $NombreServicio AppDirectory $rutaCurrent
nssm set $NombreServicio AppStdout (Join-Path $rutaLogs "servicio-stdout.log")
nssm set $NombreServicio AppStderr (Join-Path $rutaLogs "servicio-stderr.log")
nssm set $NombreServicio AppRotateFiles 1
nssm set $NombreServicio AppRotateBytes 10485760
nssm set $NombreServicio Start SERVICE_AUTO_START
nssm set $NombreServicio AppExit Default Restart

# Cuenta de servicio virtual dedicada, sin privilegios de administrador y
# sin contrasena que gestionar. Windows la crea automaticamente al primer
# 'nssm set ObjectName' con este formato.
nssm set $NombreServicio ObjectName "NT SERVICE\$NombreServicio"

Write-Host "Ajustando permisos para que la cuenta de servicio solo pueda escribir en shared\logs y shared\backups..."
$cuenta = "NT SERVICE\$NombreServicio"
icacls $rutaCurrent /grant "${cuenta}:(OI)(CI)RX" | Out-Null
icacls (Join-Path $RaizDespliegue "logs") /grant "${cuenta}:(OI)(CI)M" | Out-Null
icacls (Join-Path $RaizDespliegue "shared\backups") /grant "${cuenta}:(OI)(CI)M" | Out-Null
icacls (Join-Path $RaizDespliegue "shared\.env") /grant "${cuenta}:R" | Out-Null

nssm start $NombreServicio

Write-Host ""
Write-Host "Servicio '$NombreServicio' instalado." -ForegroundColor Green
Write-Host "Verificar con: nssm status $NombreServicio"
Write-Host "Escucha unicamente en 127.0.0.1:$Puerto -- IIS es quien debe exponerlo por HTTPS."
