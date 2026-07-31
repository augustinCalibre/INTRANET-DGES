[CmdletBinding()]
param(
    [switch]$Build
)

$ErrorActionPreference = "Stop"

function Test-CommandAvailable {
    param([Parameter(Mandatory = $true)][string]$Name)

    return $null -ne (Get-Command $Name -ErrorAction SilentlyContinue)
}

$repoRoot = Resolve-Path (Join-Path $PSScriptRoot "..\..")
Set-Location $repoRoot

if (-not (Test-CommandAvailable -Name "docker")) {
    throw "Docker n'est pas disponible. Installez Docker Desktop puis relancez ce script."
}

if (-not (Test-Path ".env")) {
    throw "Le fichier .env est absent. Copiez .env.example vers .env puis adaptez les variables réseau."
}

$requiredFiles = @(
    "docker\nginx\default.conf",
    "docker\entrypoint.sh"
)

$missingFiles = $requiredFiles | Where-Object { -not (Test-Path $_) }
if ($missingFiles.Count -gt 0) {
    throw "Fichiers Docker manquants : $($missingFiles -join ', ')"
}

$missingCerts = @(
    "docker\nginx\certs\dges-local.crt",
    "docker\nginx\certs\dges-local.key"
) | Where-Object { -not (Test-Path $_) }

if ($missingCerts.Count -gt 0) {
    Write-Warning "Certificats Nginx absents : $($missingCerts -join ', ')"
    Write-Warning "Si vous avez cloné le dépôt depuis GitHub, recopiez le dossier docker\\nginx\\certs depuis votre poste de développement."
}

$composeArgs = @("compose", "up", "-d", "--remove-orphans")
if ($Build) {
    $composeArgs += "--build"
}

Write-Host "Demarrage de la pile Docker Intranet DGES..." -ForegroundColor Cyan
& docker @composeArgs
if ($LASTEXITCODE -ne 0) {
    throw "Le demarrage Docker Compose a echoue."
}

Write-Host ""
Write-Host "Etat des services :" -ForegroundColor Green
& docker compose ps
