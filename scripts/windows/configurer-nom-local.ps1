<#
.SYNOPSIS
    Rend l'intranet accessible par son nom, intranet-dges.local.

.DESCRIPTION
    Un nom en « .local » n'est pas résolu tout seul : aucun serveur DNS ne le
    connaît. Il faut une entrée dans le fichier hosts de chaque poste qui doit
    l'utiliser. Ce script pose cette entrée.

    Sur le serveur lui-même, le nom pointe sur 127.0.0.1. Sur un poste du
    réseau, il pointe sur l'adresse du serveur — passez-la par -Adresse.

    Le script demande les droits administrateur : le fichier hosts est un
    fichier système. Il conserve une copie avant toute modification, et ne
    touche pas aux lignes qui ne le concernent pas.

.PARAMETER Adresse
    Adresse vers laquelle le nom doit pointer. 127.0.0.1 par défaut, ce qui
    convient sur la machine qui héberge la plateforme.

.PARAMETER Retirer
    Supprime les entrées au lieu de les poser.

.EXAMPLE
    .\scripts\windows\configurer-nom-local.ps1

.EXAMPLE
    .\scripts\windows\configurer-nom-local.ps1 -Adresse 192.168.100.20
#>
[CmdletBinding()]
param(
    [string]$Adresse = "127.0.0.1",
    [switch]$Retirer
)

$ErrorActionPreference = "Stop"

# Le nom retenu, sa variante sans tiret — qui se tape naturellement — et le
# nom de la messagerie.
$noms = @(
    "intranet-dges.local",
    "intranetdges.local",
    "messagerie.dges.local",
    "messageriedges.local"
)

$fichierHosts = Join-Path $env:SystemRoot "System32\drivers\etc\hosts"

# --- Droits -------------------------------------------------------------

$identite = [Security.Principal.WindowsIdentity]::GetCurrent()
$estAdministrateur = ([Security.Principal.WindowsPrincipal]$identite).IsInRole(
    [Security.Principal.WindowsBuiltInRole]::Administrator
)

if (-not $estAdministrateur) {
    Write-Host ""
    Write-Host "Droits administrateur requis." -ForegroundColor Yellow
    Write-Host "Le fichier hosts est un fichier système : Windows en interdit la"
    Write-Host "modification depuis une session ordinaire."
    Write-Host ""
    Write-Host "Rouvrez PowerShell en tant qu'administrateur, puis relancez :" -ForegroundColor Cyan
    Write-Host "  cd $((Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path)"
    Write-Host "  .\scripts\windows\configurer-nom-local.ps1$(if ($Adresse -ne '127.0.0.1') { " -Adresse $Adresse" })"
    Write-Host ""
    exit 1
}

# --- Sauvegarde ---------------------------------------------------------

$copie = "$fichierHosts.avant-intranet-dges"
Copy-Item $fichierHosts $copie -Force
Write-Host "Copie du fichier hosts : $copie" -ForegroundColor DarkGray

# --- Modification -------------------------------------------------------

# On repart des lignes existantes en retirant celles qui portent nos noms,
# puis on réécrit les nôtres. Une entrée en double, ou pointant vers une
# ancienne adresse, empêcherait la résolution sans le dire.
$lignes = Get-Content $fichierHosts
$conservees = $lignes | Where-Object {
    $ligne = $_
    -not ($noms | Where-Object { $ligne -match "\s$([regex]::Escape($_))\s*$" -or $ligne -match "\s$([regex]::Escape($_))\s" })
}

if ($Retirer) {
    Set-Content -Path $fichierHosts -Value $conservees -Encoding ASCII
    Write-Host ""
    Write-Host "Entrées retirées. L'intranet reste accessible sur https://localhost/." -ForegroundColor Green
    Write-Host ""
    exit 0
}

$nouvelles = @("", "# Intranet DGES - resolution des noms locaux")
foreach ($nom in $noms) {
    $nouvelles += "$Adresse`t$nom"
}

Set-Content -Path $fichierHosts -Value ($conservees + $nouvelles) -Encoding ASCII

Write-Host ""
Write-Host "Noms configurés vers $Adresse :" -ForegroundColor Green
foreach ($nom in $noms) { Write-Host "  $nom" }

# --- Contrôle -----------------------------------------------------------

Write-Host ""
Write-Host "Vérification de la résolution..." -ForegroundColor Cyan
# Le cache DNS de Windows garde les échecs précédents : sans purge, le nom
# resterait introuvable plusieurs minutes après avoir été déclaré.
ipconfig /flushdns | Out-Null

$echecs = @()
foreach ($nom in $noms) {
    $resolu = [System.Net.Dns]::GetHostAddresses($nom) | Where-Object { $_.AddressFamily -eq "InterNetwork" }
    if ($resolu -and $resolu[0].IPAddressToString -eq $Adresse) {
        Write-Host "  $nom -> $($resolu[0].IPAddressToString)" -ForegroundColor Green
    } else {
        $echecs += $nom
        Write-Host "  $nom : non résolu" -ForegroundColor Yellow
    }
}

Write-Host ""
if ($echecs.Count -eq 0) {
    Write-Host "L'intranet est accessible sur https://intranet-dges.local/" -ForegroundColor Green
    Write-Host "La messagerie sur https://intranet-dges.local:8443/"
    Write-Host ""
    Write-Host "Le certificat étant auto-signé, le navigateur avertira au premier accès :"
    Write-Host "c'est attendu sur un réseau interne."
} else {
    Write-Host "Certains noms ne se résolvent pas encore. Fermez et rouvrez le navigateur," -ForegroundColor Yellow
    Write-Host "puis réessayez. Si cela persiste, vérifiez le fichier :"
    Write-Host "  $fichierHosts"
}
Write-Host ""
