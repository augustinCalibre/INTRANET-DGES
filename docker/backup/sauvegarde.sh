#!/bin/sh
# ============================================================
# Sauvegarde de l'intranet DGES
#
# Produit un dossier horodate contenant :
#   - le dump de la base de l'intranet
#   - le dump de la base Nextcloud
#   - les pieces jointes (media)
#   - un manifeste rappelant la procedure de restauration
#
# Le dossier est cree automatiquement. Les sauvegardes plus anciennes que
# BACKUP_RETENTION_DAYS sont supprimees a la fin.
# ============================================================

set -eu

RACINE="${BACKUP_ROOT:-/sauvegardes}"
RETENTION="${BACKUP_RETENTION_DAYS:-14}"
INCLURE_FICHIERS_NEXTCLOUD="${BACKUP_INCLUDE_NEXTCLOUD_FILES:-0}"

HORODATAGE="$(date +%Y-%m-%d_%Hh%M)"
DESTINATION="$RACINE/$HORODATAGE"

journal() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*"
}

echec() {
    journal "ECHEC : $*"
    # Une sauvegarde incomplete est plus dangereuse qu'une absence de
    # sauvegarde : elle donne un faux sentiment de securite. On marque donc
    # explicitement le dossier.
    if [ -d "$DESTINATION" ]; then
        mv "$DESTINATION" "${DESTINATION}_INCOMPLETE" 2>/dev/null || true
    fi
    exit 1
}

journal "Début de la sauvegarde vers $DESTINATION"
mkdir -p "$DESTINATION" || echec "impossible de créer $DESTINATION"

# --- Base de l'intranet ------------------------------------------------
journal "Base de l'intranet ($POSTGRES_DB)"
PGPASSWORD="$POSTGRES_PASSWORD" pg_dump \
    --host="${POSTGRES_HOST:-db}" \
    --username="$POSTGRES_USER" \
    --format=plain \
    --no-owner \
    "$POSTGRES_DB" 2>"$DESTINATION/intranet-postgres.err" \
    | gzip > "$DESTINATION/intranet-postgres.sql.gz" \
    || echec "dump de la base de l'intranet"
[ -s "$DESTINATION/intranet-postgres.err" ] || rm -f "$DESTINATION/intranet-postgres.err"

# --- Base Nextcloud ----------------------------------------------------
if [ -n "${NEXTCLOUD_POSTGRES_DB:-}" ]; then
    journal "Base Nextcloud ($NEXTCLOUD_POSTGRES_DB)"
    PGPASSWORD="$NEXTCLOUD_POSTGRES_PASSWORD" pg_dump \
        --host="${NEXTCLOUD_POSTGRES_HOST:-nextcloud-db}" \
        --username="$NEXTCLOUD_POSTGRES_USER" \
        --format=plain \
        --no-owner \
        "$NEXTCLOUD_POSTGRES_DB" 2>"$DESTINATION/nextcloud-postgres.err" \
        | gzip > "$DESTINATION/nextcloud-postgres.sql.gz" \
        || journal "AVERTISSEMENT : dump Nextcloud impossible, on poursuit"
    [ -s "$DESTINATION/nextcloud-postgres.err" ] || rm -f "$DESTINATION/nextcloud-postgres.err"
fi

# --- Pieces jointes de l'intranet --------------------------------------
if [ -d /media-intranet ]; then
    journal "Pièces jointes (documents, courriers, diplômes)"
    tar -czf "$DESTINATION/media.tar.gz" -C /media-intranet . \
        || echec "archivage des pièces jointes"
fi

# --- Fichiers Nextcloud, seulement si demande --------------------------
# Volumineux : desactive par defaut, a activer quand la destination est un
# disque dedie.
if [ "$INCLURE_FICHIERS_NEXTCLOUD" = "1" ] && [ -d /nextcloud-data ]; then
    journal "Fichiers Nextcloud"
    tar -czf "$DESTINATION/nextcloud-data.tar.gz" -C /nextcloud-data . \
        || journal "AVERTISSEMENT : archivage Nextcloud incomplet"
fi

# --- Manifeste ---------------------------------------------------------
{
    echo "Sauvegarde de l'intranet DGES"
    echo "Date          : $(date '+%d/%m/%Y à %H:%M:%S')"
    echo "Base intranet : $POSTGRES_DB sur ${POSTGRES_HOST:-db}"
    echo "Rétention     : $RETENTION jours"
    echo
    echo "Contenu :"
    ls -lh "$DESTINATION" | tail -n +2 | awk '{printf "  %-32s %s\n", $9, $5}'
    echo
    echo "Restauration de la base de l'intranet :"
    echo "  gunzip -c intranet-postgres.sql.gz | \\"
    echo "    docker compose exec -T db psql -U $POSTGRES_USER -d $POSTGRES_DB"
    echo
    echo "Restauration des pièces jointes :"
    echo "  docker run --rm -v v1_media_data:/media -v \"\$PWD\":/sauvegarde alpine \\"
    echo "    sh -c 'cd /media && tar -xzf /sauvegarde/media.tar.gz'"
    echo
    echo "Une restauration jamais essayée n'est pas une restauration :"
    echo "testez-la au moins une fois sur une base de essai."
} > "$DESTINATION/MANIFESTE.txt"

TAILLE="$(du -sh "$DESTINATION" | cut -f1)"
journal "Sauvegarde terminée : $DESTINATION ($TAILLE)"

# --- Purge des anciennes sauvegardes -----------------------------------
if [ "$RETENTION" -gt 0 ]; then
    SUPPRIMEES=0
    for dossier in "$RACINE"/*; do
        [ -d "$dossier" ] || continue
        [ "$dossier" = "$DESTINATION" ] && continue
        if [ -n "$(find "$dossier" -maxdepth 0 -mtime "+$RETENTION" 2>/dev/null)" ]; then
            rm -rf "$dossier"
            SUPPRIMEES=$((SUPPRIMEES + 1))
        fi
    done
    [ "$SUPPRIMEES" -gt 0 ] && journal "$SUPPRIMEES sauvegarde(s) de plus de $RETENTION jours supprimée(s)"
fi

journal "Espace restant sur la destination : $(df -h "$RACINE" | tail -1 | awk '{print $4}')"
