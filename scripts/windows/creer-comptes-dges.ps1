<#
.SYNOPSIS
    Crée les services et les comptes de la DGES, intranet et messagerie.

.DESCRIPTION
    Reprend l'état du personnel décrit dans accounts/annuaire_dges.py : huit
    services, quatorze agents, chacun avec sa fonction, son rôle, son service,
    son adresse et son téléphone. Pour chaque agent, un compte intranet et un
    accès à la messagerie sont créés ensemble, avec le même identifiant et le
    même mot de passe.

    Le script peut être relancé : il ne crée que ce qui manque et ne supprime
    rien. Il ne rétablit pas le mot de passe d'un compte existant — un agent
    qui a déjà choisi le sien ne doit pas le voir revenir au mot de passe
    commun à chaque exécution.

    Les services absents de l'organigramme sont désactivés, jamais supprimés :
    un courrier imputé à un service disparu doit rester lisible.

.PARAMETER MotDePasse
    Mot de passe initial commun. Dix caractères au minimum, longueur exigée
    par la politique de mots de passe de Nextcloud. Chaque agent devra le
    changer à sa première connexion, et son nouveau mot de passe vaudra pour
    l'intranet comme pour la messagerie.

.PARAMETER DesactiverComptesDemo
    Désactive les comptes qui ne figurent pas dans l'annuaire — comptes de
    démonstration, agents partis. Ils ne sont pas supprimés : leurs courriers,
    tâches et documents gardent leur auteur.

.PARAMETER ReinitialiserMotsDePasse
    Remet le mot de passe initial sur les comptes déjà existants. À n'utiliser
    qu'avant la première distribution des accès.

.EXAMPLE
    .\scripts\windows\creer-comptes-dges.ps1

.EXAMPLE
    .\scripts\windows\creer-comptes-dges.ps1 -DesactiverComptesDemo
#>
[CmdletBinding()]
param(
    [string]$MotDePasse = "DGES-2026!",
    [switch]$DesactiverComptesDemo,
    [switch]$ReinitialiserMotsDePasse
)

$ErrorActionPreference = "Stop"

$racine = Resolve-Path (Join-Path $PSScriptRoot "..\..")
Set-Location $racine

Write-Host ""
Write-Host "Création des comptes de la DGES" -ForegroundColor White

# --- Vérifications ------------------------------------------------------

if ($MotDePasse.Length -lt 10) {
    throw "Le mot de passe initial doit faire au moins dix caractères : c'est ce qu'exige la politique de Nextcloud, et le même secret doit valoir pour l'intranet et la messagerie."
}

& docker info *> $null
if ($LASTEXITCODE -ne 0) { throw "Le démon Docker ne répond pas. Démarrez Docker Desktop puis relancez." }

$etatWeb = & docker compose ps --status running --format "{{.Service}}" 2>$null
if ($etatWeb -notcontains "web") {
    throw "Le service « web » ne tourne pas. Lancez d'abord : docker compose up -d"
}

# --- Ce que le script va faire, avant de le faire -----------------------

Write-Host ""
Write-Host "Ce script va :" -ForegroundColor Cyan
Write-Host "  - créer les 8 services de l'organigramme et désactiver les autres ;"
Write-Host "  - créer les 14 comptes agents avec leur rôle et leur service ;"
Write-Host "  - ouvrir à chacun l'accès à la messagerie ;"
Write-Host "  - créer une conversation par service."
if ($DesactiverComptesDemo) {
    Write-Host "  - désactiver les comptes absents de l'annuaire." -ForegroundColor Yellow
}
if ($ReinitialiserMotsDePasse) {
    Write-Host "  - REMETTRE le mot de passe initial sur les comptes existants." -ForegroundColor Yellow
}
Write-Host ""
Write-Host "Mot de passe initial : $MotDePasse" -ForegroundColor White
Write-Host "Chaque agent devra le changer à sa première connexion."
Write-Host ""

$reponse = Read-Host "Confirmez-vous ? (oui/non)"
if ($reponse -notin @("oui", "o", "O", "OUI", "Oui")) {
    Write-Host "Abandon. Rien n'a été modifié." -ForegroundColor Yellow
    return
}

# --- Filet de sécurité --------------------------------------------------

Write-Host ""
Write-Host "Sauvegarde avant modification..." -ForegroundColor Cyan
& docker compose exec -T backup /usr/local/bin/sauvegarde.sh
if ($LASTEXITCODE -ne 0) {
    Write-Warning "La sauvegarde a échoué. Elle n'est pas indispensable ici — le script ne supprime rien — mais vous ne pourrez pas revenir en arrière d'un seul geste."
    $suite = Read-Host "Continuer malgré tout ? (oui/non)"
    if ($suite -notin @("oui", "o", "O", "OUI", "Oui")) {
        Write-Host "Abandon. Rien n'a été modifié." -ForegroundColor Yellow
        return
    }
}

# --- Import -------------------------------------------------------------

Write-Host ""
Write-Host "Import de l'annuaire..." -ForegroundColor Cyan

$arguments = @("compose", "exec", "-T", "web", "python", "manage.py", "importer_annuaire", "--mot-de-passe", $MotDePasse)
if ($DesactiverComptesDemo) { $arguments += "--desactiver-comptes-demo" }
if ($ReinitialiserMotsDePasse) { $arguments += "--reinitialiser-mots-de-passe" }

& docker @arguments
if ($LASTEXITCODE -ne 0) {
    throw "L'import a échoué. Rien n'a été validé en base : la commande travaille dans une transaction unique."
}

# --- Récapitulatif à distribuer ----------------------------------------

Write-Host ""
Write-Host "Identifiants à distribuer" -ForegroundColor Green
Write-Host ""

& docker compose exec -T web python -c @"
import django, os
os.environ.setdefault('DJANGO_SETTINGS_MODULE','intranet_dges.settings')
django.setup()
from django.contrib.auth.models import User
from accounts.annuaire_dges import AGENTS
from accounts.constants import ROLE_CHOICES
libelles = dict(ROLE_CHOICES)
print('  %-12s %-34s %-26s %s' % ('IDENTIFIANT', 'NOM', 'ROLE', 'SERVICE'))
print('  ' + '-' * 100)
for fiche in AGENTS:
    utilisateur = User.objects.filter(username=fiche['identifiant']).first()
    if not utilisateur:
        continue
    nom = (utilisateur.get_full_name() or utilisateur.username)[:34]
    print('  %-12s %-34s %-26s %s' % (
        fiche['identifiant'], nom, libelles.get(fiche['role'], fiche['role']), fiche['service']))
"@

Write-Host ""
Write-Host "Mot de passe initial pour tous : $MotDePasse" -ForegroundColor White
Write-Host ""
Write-Host "À rappeler aux agents :" -ForegroundColor Cyan
Write-Host "  - le mot de passe est à changer à la première connexion, l'application l'impose ;"
Write-Host "  - le nouveau mot de passe vaut pour l'intranet ET pour la messagerie ;"
Write-Host "  - chacun retrouve dans la messagerie la conversation de son service"
Write-Host "    et la conversation générale de la direction."
Write-Host ""
