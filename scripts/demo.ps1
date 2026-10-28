<#
  GlobalTecnology · Entorno de prueba compartible (Windows + VS Code Ports)

  Uso (desde la raíz del proyecto):
      .\scripts\demo.ps1

  1. Activa el entorno virtual (.venv)
  2. Carga las variables de .env.tunnel
  3. migrate, collectstatic, cargar_ubicaciones y seed_demo (idempotentes)
  4. Inicia waitress en http://127.0.0.1:8000
  5. Muestra credenciales de prueba y los pasos en VS Code
#>
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

function Paso($texto) { Write-Host "`n==> $texto" -ForegroundColor Cyan }
function Ejecutar([string[]]$argumentos) {
    & python @argumentos
    if ($LASTEXITCODE -ne 0) { throw "Falló: python $($argumentos -join ' ')" }
}

# 1. Entorno virtual
Paso "Activando entorno virtual"
$activar = Join-Path $Root ".venv\Scripts\Activate.ps1"
if (-not (Test-Path $activar)) {
    Write-Host "No existe .venv. Créalo con:" -ForegroundColor Red
    Write-Host "  py -3.12 -m venv .venv" -ForegroundColor Yellow
    Write-Host "  .\.venv\Scripts\python -m pip install -r requirements.txt" -ForegroundColor Yellow
    exit 1
}
. $activar

# 2. Variables de .env.tunnel
Paso "Cargando variables de .env.tunnel"
$envFile = Join-Path $Root ".env.tunnel"
if (-not (Test-Path $envFile)) {
    Write-Host "Falta .env.tunnel. Ejecuta: Copy-Item .env.tunnel.example .env.tunnel  y complétalo." -ForegroundColor Red
    exit 1
}
Get-Content $envFile -Encoding UTF8 | ForEach-Object {
    $linea = $_.Trim()
    if ($linea -and -not $linea.StartsWith("#") -and $linea.Contains("=")) {
        $partes = $linea.Split("=", 2)
        $clave = $partes[0].Trim()
        $valor = $partes[1].Trim().Trim('"').Trim("'")
        if ($valor -eq "") {
            Remove-Item "Env:$clave" -ErrorAction SilentlyContinue
        } else {
            Set-Item -Path "Env:$clave" -Value $valor
        }
    }
}
if (-not $env:DJANGO_SETTINGS_MODULE) { $env:DJANGO_SETTINGS_MODULE = "config.settings.tunnel" }
if (-not $env:MEDIA_ROOT) { $env:MEDIA_ROOT = Join-Path $Root "media" }
$env:ENV_FILE = $envFile
$env:PYTHONUTF8 = "1"
if (-not $env:DATABASE_URL) {
    Write-Warning "DATABASE_URL vacía: se usará SQLite. La búsqueda será más básica (sin tolerancia a errores de escritura)."
}
if (-not $env:SITE_URL) {
    Write-Warning "SITE_URL vacía. Completa el paso 6 del README (URL del túnel) y reinicia este script."
}

# 3. Preparación (idempotente)
Paso "Aplicando migraciones"
Ejecutar @("manage.py", "migrate", "--noinput")
Paso "Recopilando archivos estáticos"
Ejecutar @("manage.py", "collectstatic", "--noinput", "-v", "0")
Paso "Cargando departamentos y municipios (DIVIPOLA)"
Ejecutar @("manage.py", "cargar_ubicaciones")
Paso "Cargando datos de demostración"
Ejecutar @("manage.py", "seed_demo")
Paso "Verificando configuración del túnel"
& python manage.py check_tunnel

# 5. Credenciales y recordatorio
Write-Host ""
Write-Host "==============================================================" -ForegroundColor Green
Write-Host " GlobalTecnology corriendo en http://127.0.0.1:8000" -ForegroundColor Green
Write-Host "==============================================================" -ForegroundColor Green
Write-Host " Admin (panel /panel/):  admin@globaltecnology.co  /  Admin12345!"
Write-Host " Cliente de prueba:      cliente@globaltecnology.co  /  Cliente12345!"
Write-Host ""
Write-Host " Para compartir con un enlace público:" -ForegroundColor Yellow
Write-Host "  1. VS Code > panel inferior > pestaña PORTS > Forward a Port > 8000"
Write-Host "  2. Clic derecho en el puerto > Port Visibility > Public"
Write-Host "  3. Copia la Forwarded Address en SITE_URL de .env.tunnel y reinicia (Ctrl+C y .\scripts\demo.ps1)"
Write-Host "  4. Wompi sandbox > URL de eventos: <url-del-tunel>/pagos/wompi/eventos/"
Write-Host "  El enlace funciona solo mientras este PC, VS Code y este script estén activos."
Write-Host " Ctrl+C para detener." -ForegroundColor DarkGray
Write-Host ""

# 4. Servidor (waitress funciona en Windows; gunicorn no)
#    --trusted-proxy: el túnel conecta desde 127.0.0.1 y envía X-Forwarded-Proto/Host.
#    Sin esto waitress descarta esas cabeceras y Django no sabría que la conexión es HTTPS.
& waitress-serve --listen=127.0.0.1:8000 --threads=8 `
    --trusted-proxy=127.0.0.1 `
    --trusted-proxy-headers="x-forwarded-proto x-forwarded-host x-forwarded-for" `
    config.wsgi:application
