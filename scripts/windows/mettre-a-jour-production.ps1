<#
.SYNOPSIS
    Met à jour l'intranet DGES en production, en une seule commande.

.DESCRIPTION
    Reprend la mise à jour complète dans l'ordre qui évite les mauvaises
    surprises : sauvegarder d'abord, vérifier la configuration ensuite, ne
    reconstruire qu'après, et contrôler que tout répond à la fin.

    Le script s'arrête à la première anomalie plutôt que de poursuivre sur une
    base fragile. Il ne supprime jamais rien.

    Trois pièges connus sont traités automatiquement, parce qu'ils ont coûté
    des heures :

      - le fichier .env n'est pas versionné : les variables nouvellement
        requises manquent donc en production après un git pull ;
      - nginx garde en mémoire l'adresse du conteneur web ; recréé, celui-ci
        change d'adresse et nginx répond 502 tant qu'on ne l'a pas relancé ;
      - le mot de passe d'administration de Nextcloud dans .env ne sert qu'à
        l'installation. S'il a divergé, la synchronisation de la messagerie
        échoue silencieusement.

.PARAMETER Branche
    Branche à déployer. « main » par défaut.

.PARAMETER SansSauvegarde
    Passe outre la sauvegarde préalable. À n'utiliser que si une sauvegarde
    vient d'être prise à la main.

.EXAMPLE
    .\scripts\windows\mettre-a-jour-production.ps1
#>
[CmdletBinding()]
param(
    [string]$Branche = "main",
    [switch]$SansSauvegarde
)

$ErrorActionPreference = "Stop"

# --- Utilitaires --------------------------------------------------------

function Ecrire-Etape {
    param([string]$Texte)
    Write-Host ""
    Write-Host "== $Texte" -ForegroundColor Cyan
}

function Ecrire-Ok {
    param([string]$Texte)
    Write-Host "   $Texte" -ForegroundColor Green
}

function Ecrire-Alerte {
    param([string]$Texte)
    Write-Host "   $Texte" -ForegroundColor Yellow
}

function Tester-Commande {
    param([string]$Nom)
    return $null -ne (Get-Command $Nom -ErrorAction SilentlyContinue)
}

function Invoquer-Docker {
    param([string[]]$Arguments, [string]$Erreur)
    & docker @Arguments
    if ($LASTEXITCODE -ne 0) { throw $Erreur }
}

# Certificat auto-signé : les contrôles HTTPS de fin doivent l'accepter.
function Autoriser-CertificatLocal {
    if (-not ("PolitiqueCertificatLocal" -as [type])) {
        Add-Type @"
using System.Net;
using System.Security.Cryptography.X509Certificates;
public class PolitiqueCertificatLocal : ICertificatePolicy {
    public bool CheckValidationResult(ServicePoint s, X509Certificate c, WebRequest w, int p) { return true; }
}
"@
    }
    [System.Net.ServicePointManager]::CertificatePolicy = New-Object PolitiqueCertificatLocal
    [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
}

function Obtenir-CodeHttp {
    param([string]$Url)
    try {
        $reponse = Invoke-WebRequest -Uri $Url -TimeoutSec 20 -MaximumRedirection 0 -ErrorAction Stop
        return [int]$reponse.StatusCode
    } catch {
        if ($_.Exception.Response) { return [int]$_.Exception.Response.StatusCode }
        return 0
    }
}

# --- Préparation --------------------------------------------------------

$racine = Resolve-Path (Join-Path $PSScriptRoot "..\..")
Set-Location $racine

Write-Host ""
Write-Host "Mise à jour de l'intranet DGES" -ForegroundColor White
Write-Host "Dossier : $racine"

Ecrire-Etape "Vérifications préalables"

if (-not (Tester-Commande -Nom "git")) { throw "Git n'est pas installé sur cette machine." }
if (-not (Tester-Commande -Nom "docker")) { throw "Docker n'est pas disponible. Démarrez Docker Desktop." }
if (-not (Test-Path ".git")) { throw "Ce dossier n'est pas un clone Git. Clonez le dépôt avant de mettre à jour." }
if (-not (Test-Path ".env")) { throw "Le fichier .env est absent. Sans lui, ni la base ni la messagerie ne démarrent." }

& docker info *> $null
if ($LASTEXITCODE -ne 0) { throw "Le démon Docker ne répond pas. Démarrez Docker Desktop puis relancez." }

$modifications = & git status --porcelain
if ($LASTEXITCODE -ne 0) { throw "Impossible de lire l'état Git du projet." }
if ($modifications) {
    Write-Host $modifications
    throw "Des modifications locales non validées sont présentes. Le serveur ne doit pas être modifié directement : annulez-les avant de mettre à jour."
}
Ecrire-Ok "Dépôt propre, Docker disponible."

# --- Sauvegarde ---------------------------------------------------------

if ($SansSauvegarde) {
    Ecrire-Alerte "Sauvegarde préalable ignorée à votre demande."
} else {
    Ecrire-Etape "Sauvegarde avant toute modification"
    & docker compose exec -T backup /usr/local/bin/sauvegarde.sh
    if ($LASTEXITCODE -ne 0) {
        throw "La sauvegarde a échoué. Mise à jour interrompue : on ne modifie pas une installation qu'on ne saurait pas restaurer. Vérifiez le disque de sauvegarde, puis relancez."
    }
    Ecrire-Ok "Sauvegarde prise."
}

# --- Récupération du code ----------------------------------------------

Ecrire-Etape "Récupération des changements ($Branche)"

& git fetch origin $Branche
if ($LASTEXITCODE -ne 0) { throw "Le git fetch a échoué. Vérifiez l'accès au dépôt." }

& git checkout $Branche
if ($LASTEXITCODE -ne 0) { throw "Impossible de basculer sur la branche $Branche." }

& git pull --ff-only origin $Branche
if ($LASTEXITCODE -ne 0) { throw "Le git pull a échoué." }

$version = (& git log -1 --pretty=format:"%h %s")
Ecrire-Ok "Version déployée : $version"

# --- Configuration : ce que le dépôt ne peut pas apporter ---------------

Ecrire-Etape "Contrôle du fichier .env"

$env_contenu = Get-Content ".env" -Raw
$env_modifie = $false

# La messagerie appelle Nextcloud par le réseau Docker interne. Sans ce nom
# dans les domaines de confiance, Nextcloud refuse chaque appel.
$ligneDomaines = Select-String -Path ".env" -Pattern "^NEXTCLOUD_TRUSTED_DOMAINS=" | Select-Object -First 1
if ($null -eq $ligneDomaines) {
    Ecrire-Alerte "NEXTCLOUD_TRUSTED_DOMAINS est absent du .env : la messagerie ne pourra pas être synchronisée."
} elseif ($ligneDomaines.Line -notmatch "nextcloud-app") {
    Copy-Item ".env" ".env.avant-mise-a-jour" -Force
    $nouvelle = $ligneDomaines.Line -replace "^NEXTCLOUD_TRUSTED_DOMAINS=", "NEXTCLOUD_TRUSTED_DOMAINS=nextcloud-app "
    $env_contenu = $env_contenu.Replace($ligneDomaines.Line, $nouvelle)
    $env_modifie = $true
    Ecrire-Alerte "« nextcloud-app » ajouté aux domaines de confiance Nextcloud (copie de l'ancien .env dans .env.avant-mise-a-jour)."
}

if ($env_modifie) {
    Set-Content -Path ".env" -Value $env_contenu -Encoding UTF8 -NoNewline
}
Ecrire-Ok "Configuration contrôlée."

# --- Reconstruction et démarrage ---------------------------------------

Ecrire-Etape "Reconstruction des images"
Invoquer-Docker -Arguments @("compose", "build", "web", "backup") -Erreur "La construction des images a échoué."
Ecrire-Ok "Images à jour."

Ecrire-Etape "Démarrage de la pile"
Invoquer-Docker -Arguments @("compose", "up", "-d", "--remove-orphans") -Erreur "Le démarrage Docker Compose a échoué."

# Les migrations sont appliquées par le point d'entrée du conteneur web : il
# faut lui laisser le temps de finir avant de contrôler quoi que ce soit.
Write-Host "   Attente de l'application des migrations..."
Start-Sleep -Seconds 30

# nginx garde l'ancienne adresse du conteneur web et répondrait 502.
Invoquer-Docker -Arguments @("compose", "restart", "nginx") -Erreur "Le redémarrage de nginx a échoué."
Start-Sleep -Seconds 8
Ecrire-Ok "Pile démarrée."

# --- Contrôles ----------------------------------------------------------

Ecrire-Etape "Contrôles de bon fonctionnement"
Autoriser-CertificatLocal

$anomalies = @()

$codeIntranet = Obtenir-CodeHttp -Url "https://localhost/"
if ($codeIntranet -ge 200 -and $codeIntranet -lt 400) {
    Ecrire-Ok "Intranet : répond (HTTP $codeIntranet)."
} else {
    $anomalies += "L'intranet ne répond pas (HTTP $codeIntranet). Voyez : docker compose logs web --tail 50"
}

$codeMessagerie = Obtenir-CodeHttp -Url "https://localhost:8443/"
if ($codeMessagerie -ge 200 -and $codeMessagerie -lt 400) {
    Ecrire-Ok "Messagerie : répond (HTTP $codeMessagerie)."
} else {
    $anomalies += "La messagerie ne répond pas (HTTP $codeMessagerie). Voyez : docker compose logs nextcloud-app --tail 50"
}

$diagnostic = & docker compose exec -T web python -c @"
import django, os
os.environ.setdefault('DJANGO_SETTINGS_MODULE','intranet_dges.settings')
django.setup()
from exploitation import services as sauvegarde
from messagerie import client
print('sauvegarde=' + sauvegarde.diagnostic_destination()['etat'])
print('messagerie=' + client.diagnostic()['etat'])
"@ 2>$null

$etatSauvegarde = ($diagnostic | Select-String "^sauvegarde=").ToString() -replace "^sauvegarde=", ""
$etatMessagerie = ($diagnostic | Select-String "^messagerie=").ToString() -replace "^messagerie=", ""

if ($etatSauvegarde -eq "ok") {
    Ecrire-Ok "Disque de sauvegarde : joignable."
} else {
    $anomalies += "Disque de sauvegarde : $etatSauvegarde. Ouvrez l'onglet « Sauvegarde et restauration » pour le détail."
}

if ($etatMessagerie -eq "ok") {
    Ecrire-Ok "Messagerie : synchronisation opérationnelle."
} else {
    $anomalies += @"
Synchronisation de la messagerie : $etatMessagerie.
   Si les identifiants sont refusés, c'est que le mot de passe d'administration
   de Nextcloud a divergé de celui du .env. On les réaligne par :
     docker compose exec -u www-data nextcloud-app php occ user:resetpassword admin_dges
   en saisissant la valeur de NEXTCLOUD_ADMIN_PASSWORD du fichier .env.
"@
}

# --- Conclusion ---------------------------------------------------------

Write-Host ""
if ($anomalies.Count -eq 0) {
    Write-Host "Mise à jour terminée. Tout répond." -ForegroundColor Green
    Write-Host "Version : $version"
} else {
    Write-Host "Mise à jour appliquée, mais des points restent à traiter :" -ForegroundColor Yellow
    foreach ($anomalie in $anomalies) {
        Write-Host ""
        Write-Host " - $anomalie" -ForegroundColor Yellow
    }
    Write-Host ""
    Write-Host "La sauvegarde prise en début de script permet de revenir en arrière si besoin :" -ForegroundColor Yellow
    Write-Host "voir docs/RESTAURATION.md."
}
Write-Host ""
