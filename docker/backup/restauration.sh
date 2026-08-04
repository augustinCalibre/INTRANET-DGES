#!/bin/sh
# ============================================================
# Restauration de l'intranet DGES depuis une archive de sauvegarde
#
#   restauration.sh sauvegarde_2026-08-04_01h00.zip
#
# Portee : la base de l'application et les pieces jointes. La messagerie
# Nextcloud n'est PAS restauree ici — il faudrait arreter ses conteneurs, ce
# qu'un conteneur ne peut pas faire pour un autre sans acces au socket Docker,
# et une messagerie a moitie restauree est pire qu'une messagerie intacte. La
# procedure Nextcloud est dans docs/RESTAURATION.md.
#
# Deux precautions structurent ce script :
#
#   1. Une sauvegarde de l'etat actuel est prise AVANT toute destruction. Se
#      tromper d'archive est l'erreur la plus probable ; sans ce filet, elle
#      est irrattrapable.
#   2. Les pieces jointes ne sont remplacees qu'une fois extraites et
#      completes. A aucun moment le dossier n'est vide en attendant la suite.
# ============================================================

set -eu

RACINE="${BACKUP_ROOT:-/sauvegardes}"
CONTROLE="${BACKUP_CONTROL_DIR:-/controle}"
NOM_ARCHIVE="${1:-}"
ARCHIVE="$RACINE/$NOM_ARCHIVE"
TRAVAIL="$RACINE/.restauration-en-cours"

journal() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] restauration : $*"
}

# Etat lisible par l'application, qui l'affiche a l'ecran pendant l'operation.
# Format « cle=valeur », une ligne par cle : ecrire du JSON a la main en shell
# demande d'echapper guillemets et antislashs, et un seul oubli rendrait
# l'etat illisible au pire moment.
#
# Le fichier est ecrit a cote puis deplace : l'application ne peut jamais en
# lire une version a moitie ecrite.
etat() {
    {
        echo "operation=restauration"
        echo "archive=$NOM_ARCHIVE"
        echo "etape=$1"
        echo "message=$2"
        echo "horodatage=$(date '+%Y-%m-%d %H:%M:%S')"
        echo "demandeur=${DEMANDEUR:-}"
    } > "$CONTROLE/etat.tmp" 2>/dev/null || return 0
    mv "$CONTROLE/etat.tmp" "$CONTROLE/etat" 2>/dev/null || true
}

# Trace durable des operations. Elle vit sur le disque de sauvegarde et non en
# base : une restauration remplace la base, et un historique qui disparait avec
# l'operation qu'il devait tracer ne sert a rien.
historique() {
    printf '%s|restauration|%s|%s|%s\n' \
        "$(date '+%Y-%m-%d %H:%M:%S')" "$NOM_ARCHIVE" "$1" "${DEMANDEUR:-}" \
        >> "$CONTROLE/journal.txt" 2>/dev/null || true
}

maintenance_activer() {
    date '+%Y-%m-%d %H:%M:%S' > "$CONTROLE/maintenance" 2>/dev/null || true
}

maintenance_lever() {
    rm -f "$CONTROLE/maintenance" 2>/dev/null || true
}

nettoyer() {
    rm -rf "$TRAVAIL" 2>/dev/null || true
}

echec() {
    journal "ECHEC : $*"
    etat "echec" "$1"
    historique "echec : $1"
    nettoyer
    maintenance_lever
    exit 1
}

# --- Verifications prealables ------------------------------------------
[ -n "$NOM_ARCHIVE" ] || echec "aucune archive indiquée"

# Le nom vient d'une requete web : on refuse tout ce qui pourrait designer un
# fichier hors du dossier de sauvegarde.
case "$NOM_ARCHIVE" in
    */*|*..*|"") echec "nom d archive invalide" ;;
esac

[ -f "$ARCHIVE" ] || echec "archive introuvable : $NOM_ARCHIVE"

journal "Restauration demandée depuis $NOM_ARCHIVE"
etat "verification" "Vérification de l archive"

unzip -tq "$ARCHIVE" >/dev/null 2>&1 || echec "archive illisible ou endommagée"

nettoyer
mkdir -p "$TRAVAIL" || echec "impossible de préparer le dossier de travail"

unzip -q "$ARCHIVE" -d "$TRAVAIL" || echec "extraction de l archive"

[ -f "$TRAVAIL/intranet-postgres.sql.gz" ] \
    || echec "cette archive ne contient pas de base de l intranet"

# --- 1. Filet de securite ----------------------------------------------
journal "Sauvegarde de l'état actuel avant toute modification"
etat "filet" "Sauvegarde de l état actuel, par précaution"

if ! /usr/local/bin/sauvegarde.sh > /tmp/filet.log 2>&1; then
    tail -3 /tmp/filet.log | while read -r ligne; do journal "  $ligne"; done
    echec "la sauvegarde de securite a echoue, restauration annulee"
fi

# --- 2. Fermeture de l'application -------------------------------------
journal "Mise en maintenance de l'application"
etat "maintenance" "Mise en maintenance de l application"
maintenance_activer

# Laisse aux requetes en cours le temps de se terminer avant de couper.
sleep 3

# --- 3. Base de l'application ------------------------------------------
journal "Restauration de la base $POSTGRES_DB"
etat "base" "Restauration de la base de données"

export PGPASSWORD="$POSTGRES_PASSWORD"
PSQL_ADMIN="psql -h ${POSTGRES_HOST:-db} -U $POSTGRES_USER -d postgres -q"

# Les connexions de l'application empechent la suppression de la base. Le mode
# maintenance les tarit, mais celles deja ouvertes survivent : on les coupe.
$PSQL_ADMIN -c "select pg_terminate_backend(pid) from pg_stat_activity where datname = '$POSTGRES_DB' and pid <> pg_backend_pid();" > /dev/null 2>&1 || true

$PSQL_ADMIN -c "DROP DATABASE IF EXISTS \"$POSTGRES_DB\";" > /dev/null \
    || echec "impossible de remplacer la base existante"
$PSQL_ADMIN -c "CREATE DATABASE \"$POSTGRES_DB\";" > /dev/null \
    || echec "impossible de creer la base"

gunzip -c "$TRAVAIL/intranet-postgres.sql.gz" \
    | psql -h "${POSTGRES_HOST:-db}" -U "$POSTGRES_USER" -d "$POSTGRES_DB" \
        -q -v ON_ERROR_STOP=1 > /dev/null \
    || echec "le chargement de la base a echoue, voir les journaux du service"

# --- 4. Pieces jointes -------------------------------------------------
if [ -f "$TRAVAIL/media.tar.gz" ] && [ -d /media-intranet ]; then
    journal "Restauration des pièces jointes"
    etat "media" "Restauration des pièces jointes"

    NOUVEAU="/media-intranet/.restauration-nouveau"
    ANCIEN="/media-intranet/.restauration-ancien"
    rm -rf "$NOUVEAU" "$ANCIEN"
    mkdir -p "$NOUVEAU" "$ANCIEN"

    # On extrait d'abord, entierement. Les fichiers en place ne sont touches
    # qu'une fois la nouvelle version disponible sur le disque.
    tar -xzf "$TRAVAIL/media.tar.gz" -C "$NOUVEAU" \
        || echec "extraction des pieces jointes"

    find /media-intranet -mindepth 1 -maxdepth 1 \
        ! -name .restauration-nouveau ! -name .restauration-ancien \
        -exec mv {} "$ANCIEN/" \; 2>/dev/null || true
    find "$NOUVEAU" -mindepth 1 -maxdepth 1 \
        -exec mv {} /media-intranet/ \; 2>/dev/null || true

    rm -rf "$NOUVEAU" "$ANCIEN"
fi

# --- 5. Reouverture ----------------------------------------------------
journal "Réouverture de l'application"
maintenance_lever
nettoyer

etat "termine" "Restauration terminée"
historique "succes"
journal "Restauration terminée depuis $NOM_ARCHIVE"
