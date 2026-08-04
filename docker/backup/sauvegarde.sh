#!/bin/sh
# ============================================================
# Sauvegarde de l'intranet DGES
#
# Produit UNE archive : sauvegarde_AAAA-MM-JJ_HHhMM.zip
#
#   intranet-postgres.sql.gz      base de l'application
#   nextcloud-postgres.sql.gz     base de la messagerie
#   media.tar.gz                  pieces jointes
#   nextcloud-data.tar.gz         fichiers de la messagerie
#   configuration/env.txt         mots de passe et cle secrete
#   configuration/certificats.tar.gz
#   configuration/nextcloud-config.tar.gz
#   MANIFESTE.txt
#
# L'archive n'apparait dans le dossier de destination qu'une fois complete :
# le travail se fait dans un dossier de chantier cache, et le fichier final
# est deplace en une seule operation. Une archive presente est donc toujours
# une archive utilisable — la question « celle-ci est-elle complete ? » ne se
# pose plus.
# ============================================================

set -eu

RACINE="${BACKUP_ROOT:-/sauvegardes}"
RETENTION="${BACKUP_RETENTION_DAYS:-14}"
INCLURE_FICHIERS_NEXTCLOUD="${BACKUP_INCLUDE_NEXTCLOUD_FILES:-0}"

HORODATAGE="$(date +%Y-%m-%d_%Hh%M)"
NOM_ARCHIVE="sauvegarde_$HORODATAGE.zip"
ARCHIVE="$RACINE/$NOM_ARCHIVE"
CHANTIER="$RACINE/.chantier-$HORODATAGE"

journal() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*"
}

nettoyer() {
    rm -rf "$CHANTIER" "$CHANTIER.zip" 2>/dev/null || true
}

echec() {
    journal "ECHEC : $*"
    # Rien d'incomplet ne subsiste : ni archive tronquee, ni dossier a moitie
    # rempli qu'on pourrait prendre pour une sauvegarde valable.
    nettoyer
    exit 1
}

journal "Début de la sauvegarde"

if [ -e "$ARCHIVE" ]; then
    # Deux sauvegardes dans la meme minute : on ne remplace pas la premiere.
    HORODATAGE="${HORODATAGE}_$(date +%S)s"
    NOM_ARCHIVE="sauvegarde_$HORODATAGE.zip"
    ARCHIVE="$RACINE/$NOM_ARCHIVE"
    CHANTIER="$RACINE/.chantier-$HORODATAGE"
fi

mkdir -p "$CHANTIER" || echec "impossible de créer le dossier de travail dans $RACINE"

# --- Controle de la destination avant d'ecrire quoi que ce soit ---------
#
# Une destination mal montee est le piege le plus vicieux : Docker cree
# silencieusement un dossier dans sa machine virtuelle quand il ne sait pas
# resoudre un disque de l'hote — un disque externe en exFAT, ou branche apres
# le demarrage de Docker. La sauvegarde parait fonctionner, remplit quelques
# dizaines de megaoctets, et rien n'arrive sur le disque vise.
ESPACE_MINIMAL_KO="${BACKUP_MIN_FREE_KB:-524288}"
ESPACE_DISPONIBLE_KO="$(df -Pk "$CHANTIER" | tail -1 | awk '{print $4}')"

if [ -z "$ESPACE_DISPONIBLE_KO" ]; then
    echec "impossible de mesurer l'espace disponible sur $RACINE"
fi

if [ "$ESPACE_DISPONIBLE_KO" -lt "$ESPACE_MINIMAL_KO" ]; then
    echec "espace insuffisant sur la destination : $(( ESPACE_DISPONIBLE_KO / 1024 )) Mo disponibles, $(( ESPACE_MINIMAL_KO / 1024 )) Mo requis. Vérifiez que BACKUP_DIR pointe bien sur le disque prévu et que Docker sait le monter."
fi

# --- Base de l'intranet ------------------------------------------------
journal "Base de l'intranet ($POSTGRES_DB)"
PGPASSWORD="$POSTGRES_PASSWORD" pg_dump \
    --host="${POSTGRES_HOST:-db}" \
    --username="$POSTGRES_USER" \
    --format=plain \
    --no-owner \
    "$POSTGRES_DB" 2>"$CHANTIER/intranet-postgres.err" \
    | gzip > "$CHANTIER/intranet-postgres.sql.gz" \
    || echec "dump de la base de l'intranet"
[ -s "$CHANTIER/intranet-postgres.err" ] || rm -f "$CHANTIER/intranet-postgres.err"

# --- Base Nextcloud ----------------------------------------------------
if [ -n "${NEXTCLOUD_POSTGRES_DB:-}" ]; then
    journal "Base Nextcloud ($NEXTCLOUD_POSTGRES_DB)"
    PGPASSWORD="$NEXTCLOUD_POSTGRES_PASSWORD" pg_dump \
        --host="${NEXTCLOUD_POSTGRES_HOST:-nextcloud-db}" \
        --username="$NEXTCLOUD_POSTGRES_USER" \
        --format=plain \
        --no-owner \
        "$NEXTCLOUD_POSTGRES_DB" 2>"$CHANTIER/nextcloud-postgres.err" \
        | gzip > "$CHANTIER/nextcloud-postgres.sql.gz" \
        || journal "AVERTISSEMENT : dump Nextcloud impossible, on poursuit"
    [ -s "$CHANTIER/nextcloud-postgres.err" ] || rm -f "$CHANTIER/nextcloud-postgres.err"
fi

# --- Pieces jointes de l'intranet --------------------------------------
if [ -d /media-intranet ]; then
    journal "Pièces jointes (documents, courriers, diplômes)"
    tar -czf "$CHANTIER/media.tar.gz" -C /media-intranet . \
        || echec "archivage des pièces jointes"
fi

# --- Fichiers Nextcloud, seulement si demande --------------------------
if [ "$INCLURE_FICHIERS_NEXTCLOUD" = "1" ] && [ -d /nextcloud-data ]; then
    journal "Fichiers Nextcloud"
    # Un archivage interrompu, faute de place le plus souvent, laisse aussi
    # planer un doute sur les fichiers ecrits avant lui : on echoue au lieu
    # d'avertir.
    tar -czf "$CHANTIER/nextcloud-data.tar.gz" -C /nextcloud-data . \
        || echec "archivage des fichiers Nextcloud"
fi

# --- Configuration absente de Git --------------------------------------
#
# Les dumps et les pieces jointes ne suffisent pas a repartir d'une machine
# neuve. Il y manque le fichier .env — mots de passe des bases, cle secrete
# Django — les certificats TLS, et surtout le config.php de Nextcloud : il
# porte « passwordsalt » et « secret », sans lesquels la base Nextcloud
# restauree est inexploitable, les mots de passe ne se verifiant plus.
journal "Configuration (.env, certificats, config Nextcloud)"
mkdir -p "$CHANTIER/configuration"

if [ -f /projet/.env ]; then
    cp /projet/.env "$CHANTIER/configuration/env.txt" \
        || echec "copie du fichier .env"
else
    journal "AVERTISSEMENT : fichier .env introuvable, non sauvegardé"
fi

if [ -d /projet/docker/nginx/certs ]; then
    tar -czf "$CHANTIER/configuration/certificats.tar.gz" \
        -C /projet/docker/nginx/certs . 2>/dev/null \
        || journal "AVERTISSEMENT : certificats non archivés (ils sont régénérables)"
fi

if [ -d /nextcloud-config ]; then
    tar -czf "$CHANTIER/configuration/nextcloud-config.tar.gz" \
        -C /nextcloud-config . \
        || echec "archivage de la configuration Nextcloud"
fi

# --- Manifeste ---------------------------------------------------------
{
    echo "Sauvegarde de l'intranet DGES"
    echo "Date          : $(date '+%d/%m/%Y à %H:%M:%S')"
    echo "Base intranet : $POSTGRES_DB sur ${POSTGRES_HOST:-db}"
    echo "Rétention     : $RETENTION jours"
    echo
    echo "Contenu :"
    ls -lh "$CHANTIER" | tail -n +2 | awk '{printf "  %-32s %s\n", $9, $5}'
    echo
    echo "ATTENTION : le dossier « configuration » contient des mots de passe"
    echo "en clair. Gardez cette archive comme un dossier du personnel."
    echo
    echo "RESTAURATION"
    echo "  Le plus simple : dans l'intranet, onglet « Sauvegarde et"
    echo "  restauration », bouton Restaurer en face de cette archive."
    echo
    echo "  À la main, ou depuis une machine neuve : docs/RESTAURATION.md"
    echo "  dans le dépôt du projet."
    echo
    echo "Une restauration jamais essayée n'est pas une restauration :"
    echo "testez-la au moins une fois sur une base d'essai."
} > "$CHANTIER/MANIFESTE.txt"

# --- Assemblage de l'archive -------------------------------------------
#
# On zippe a cote, puis on deplace : le deplacement sur un meme systeme de
# fichiers est instantane et indivisible. Une archive visible dans le dossier
# est donc toujours complete, meme si la machine s'eteint pendant l'operation.
journal "Assemblage de l'archive"
( cd "$CHANTIER" && zip -q -r -X "$CHANTIER.zip" . ) \
    || echec "assemblage de l'archive ZIP"

mv "$CHANTIER.zip" "$ARCHIVE" || echec "mise en place de l'archive"
rm -rf "$CHANTIER"

TAILLE="$(du -h "$ARCHIVE" | cut -f1)"
journal "Sauvegarde terminée : $NOM_ARCHIVE ($TAILLE)"

# --- Purge des anciennes sauvegardes -----------------------------------
if [ "$RETENTION" -gt 0 ]; then
    SUPPRIMEES=0
    for ancienne in "$RACINE"/sauvegarde_*.zip; do
        [ -f "$ancienne" ] || continue
        [ "$ancienne" = "$ARCHIVE" ] && continue
        if [ -n "$(find "$ancienne" -maxdepth 0 -mtime "+$RETENTION" 2>/dev/null)" ]; then
            rm -f "$ancienne"
            SUPPRIMEES=$((SUPPRIMEES + 1))
        fi
    done
    # Sauvegardes de l'ancien format, en dossiers, purgees selon la meme regle.
    for dossier in "$RACINE"/????-??-??_??h??; do
        [ -d "$dossier" ] || continue
        if [ -n "$(find "$dossier" -maxdepth 0 -mtime "+$RETENTION" 2>/dev/null)" ]; then
            rm -rf "$dossier"
            SUPPRIMEES=$((SUPPRIMEES + 1))
        fi
    done
    [ "$SUPPRIMEES" -gt 0 ] && journal "$SUPPRIMEES sauvegarde(s) de plus de $RETENTION jours supprimée(s)"
fi

journal "Espace restant sur la destination : $(df -h "$RACINE" | tail -1 | awk '{print $4}')"
