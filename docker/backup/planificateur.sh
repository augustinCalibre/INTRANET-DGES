#!/bin/sh
# ============================================================
# Planificateur de la sauvegarde quotidienne
#
# Attend l'heure fixee par BACKUP_HOUR, lance la sauvegarde, recommence.
#
# Pas de cron : le conteneur ne fait que cela, une boucle explicite se lit et
# se depanne plus facilement qu'une crontab dans une image. Le conteneur est
# relance par Docker apres un redemarrage de la machine, donc la planification
# survit aux coupures.
# ============================================================

set -eu

HEURE_CIBLE="${BACKUP_HOUR:-1}"
LANCER_AU_DEMARRAGE="${BACKUP_ON_START:-0}"

journal() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] planificateur : $*"
}

# `10#` force la base decimale : sans cela « 08 » et « 09 » seraient lus comme
# des nombres octaux invalides et la boucle s'arreterait a huit heures.
secondes_avant_prochaine_execution() {
    heure=$(date +%H)
    minute=$(date +%M)
    seconde=$(date +%S)
    ecoulees=$(( 10#$heure * 3600 + 10#$minute * 60 + 10#$seconde ))
    cible=$(( 10#$HEURE_CIBLE * 3600 ))

    if [ "$cible" -gt "$ecoulees" ]; then
        echo $(( cible - ecoulees ))
    else
        echo $(( 86400 - ecoulees + cible ))
    fi
}

journal "démarré — sauvegarde quotidienne à ${HEURE_CIBLE}h00, destination ${BACKUP_ROOT:-/sauvegardes}"

if [ "$LANCER_AU_DEMARRAGE" = "1" ]; then
    journal "sauvegarde immédiate demandée au démarrage"
    /usr/local/bin/sauvegarde.sh || journal "la sauvegarde de démarrage a échoué"
fi

while true; do
    attente=$(secondes_avant_prochaine_execution)
    journal "prochaine sauvegarde dans $(( attente / 3600 ))h$(( (attente % 3600) / 60 ))"
    sleep "$attente"

    /usr/local/bin/sauvegarde.sh || journal "la sauvegarde a échoué, nouvelle tentative demain"

    # Evite de repartir dans la meme seconde et de sauvegarder deux fois.
    sleep 60
done
