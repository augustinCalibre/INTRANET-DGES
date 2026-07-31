[CmdletBinding()]
param(
    [string]$Branch = "main",
    [switch]$Build
)

$ErrorActionPreference = "Stop"

function Test-CommandAvailable {
    param([Parameter(Mandatory = $true)][string]$Name)

    return $null -ne (Get-Command $Name -ErrorAction SilentlyContinue)
}

$repoRoot = Resolve-Path (Join-Path $PSScriptRoot "..\..")
Set-Location $repoRoot

if (-not (Test-Path ".git")) {
    throw "Ce dossier n'est pas un clone Git. Clonez d'abord le depot GitHub sur le serveur."
}

if (-not (Test-CommandAvailable -Name "git")) {
    throw "Git n'est pas disponible sur cette machine."
}

$status = & git status --porcelain
if ($LASTEXITCODE -ne 0) {
    throw "Impossible de lire l'etat Git du projet."
}

if ($status) {
    throw "Des modifications locales non commitees sont presentes sur le serveur. Nettoyez-les avant le git pull."
}

Write-Host "Recuperation des changements depuis GitHub ($Branch)..." -ForegroundColor Cyan
& git fetch origin $Branch
if ($LASTEXITCODE -ne 0) {
    throw "Le git fetch a echoue."
}

& git checkout $Branch
if ($LASTEXITCODE -ne 0) {
    throw "Impossible de basculer sur la branche $Branch."
}

& git pull --ff-only origin $Branch
if ($LASTEXITCODE -ne 0) {
    throw "Le git pull a echoue."
}

$startScript = Join-Path $PSScriptRoot "start-local-stack.ps1"
if ($Build) {
    & $startScript -Build
} else {
    & $startScript
}
