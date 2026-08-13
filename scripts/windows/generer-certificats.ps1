<#
.SYNOPSIS
    Génère les certificats TLS de l'intranet DGES.

.DESCRIPTION
    Le certificat et sa clé ne sont pas versionnés, et ne doivent pas l'être :
    la clé privée signe l'identité du serveur. Un dépôt Git se clone, se copie
    et se partage — ce n'est pas un endroit pour un secret.

    Seule la configuration est versionnée. Ce script la reprend pour produire
    un certificat équivalent sur n'importe quelle machine, ce qui évite d'avoir
    à transporter la clé d'un poste à l'autre.

    Les noms couverts sont ceux de docker/nginx/certs/openssl-dges-local.cnf :
    intranet-dges.local, messagerie.dges.local, leurs variantes sans tiret,
    localhost et les adresses locales.

    Le certificat est auto-signé : le navigateur avertit au premier accès. Sur
    un réseau interne sans autorité de certification, c'est attendu.

.PARAMETER Remplacer
    Régénère même si des certificats existent déjà. Les navigateurs
    redemanderont alors d'accepter le nouveau.

.PARAMETER Jours
    Durée de validité. Dix ans par défaut : un certificat interne qui expire
    un matin sans prévenir coûte plus cher qu'il ne protège.

.EXAMPLE
    .\scripts\windows\generer-certificats.ps1

.EXAMPLE
    .\scripts\windows\generer-certificats.ps1 -Remplacer
#>
[CmdletBinding()]
param(
    [switch]$Remplacer,
    [int]$Jours = 3650
)

$ErrorActionPreference = "Stop"

$racine = Resolve-Path (Join-Path $PSScriptRoot "..\..")
Set-Location $racine

$dossier = Join-Path $racine "docker\nginx\certs"
$configuration = Join-Path $dossier "openssl-dges-local.cnf"
$certificat = Join-Path $dossier "dges-local.crt"
$cle = Join-Path $dossier "dges-local.key"

Write-Host ""
Write-Host "Certificats TLS de l'intranet DGES" -ForegroundColor White

if (-not (Test-Path $configuration)) {
    throw "Configuration introuvable : $configuration. Le dépôt est-il complet ?"
}

& docker info *> $null
if ($LASTEXITCODE -ne 0) {
    throw "Le démon Docker ne répond pas. Démarrez Docker Desktop puis relancez."
}

# --- Faut-il regenerer ? ------------------------------------------------

if ((Test-Path $certificat) -and (Test-Path $cle) -and -not $Remplacer) {
    Write-Host ""
    Write-Host "Des certificats sont déjà en place :" -ForegroundColor Green
    & docker run --rm -v "${dossier}:/certs" alpine sh -c `
        "apk add --no-cache openssl >/dev/null 2>&1 && openssl x509 -in /certs/dges-local.crt -noout -subject -dates -ext subjectAltName"
    Write-Host ""
    Write-Host "Rien à faire. Pour les remplacer malgré tout :" -ForegroundColor Cyan
    Write-Host "  .\scripts\windows\generer-certificats.ps1 -Remplacer"
    Write-Host ""
    return
}

# --- Sauvegarde de l'existant -------------------------------------------

if (Test-Path $certificat) {
    $horodatage = Get-Date -Format "yyyyMMdd-HHmmss"
    Copy-Item $certificat "$certificat.$horodatage" -Force
    Copy-Item $cle "$cle.$horodatage" -Force
    Write-Host "Anciens certificats conservés avec le suffixe .$horodatage" -ForegroundColor DarkGray
}

# --- Generation ---------------------------------------------------------

Write-Host ""
Write-Host "Génération..." -ForegroundColor Cyan

& docker run --rm -v "${dossier}:/certs" alpine sh -c `
    "apk add --no-cache openssl >/dev/null 2>&1 && openssl req -x509 -nodes -days $Jours -newkey rsa:2048 -keyout /certs/dges-local.key -out /certs/dges-local.crt -config /certs/openssl-dges-local.cnf 2>/dev/null && echo genere"

if ($LASTEXITCODE -ne 0) {
    throw "La génération a échoué."
}

Write-Host ""
Write-Host "Certificat produit :" -ForegroundColor Green
& docker run --rm -v "${dossier}:/certs" alpine sh -c `
    "apk add --no-cache openssl >/dev/null 2>&1 && openssl x509 -in /certs/dges-local.crt -noout -subject -dates -ext subjectAltName"

# --- Prise en compte ----------------------------------------------------

Write-Host ""
Write-Host "nginx doit être relancé pour servir le nouveau certificat :" -ForegroundColor Cyan
Write-Host "  docker compose restart nginx"
Write-Host ""
Write-Host "Les navigateurs redemanderont de l'accepter au premier accès." -ForegroundColor Yellow
Write-Host ""
