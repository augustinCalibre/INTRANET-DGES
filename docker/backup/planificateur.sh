#!/bin/sh
# ============================================================
# Planificateur de la sauvegarde quotidienne
#
# Principe : verifier l'heure reelle toutes les cinq minutes, et sauvegarder
# des qu'un nouveau jour est entame et que l'heure cible est passee.
#
# Pourquoi pas un simple « dormir jusqu'a 1h00 » : quand la machine se met en
# veille ou hiberne, le conteneur est gele et le compte a rebours s'arrete avec
# lui. Au reveil il resterait des heures a attendre, et la sauvegarde de la
# nuit serait purement et simplement perdue. Ici, un poste rallume a 8h00
# rattrape immediatement la sauvegarde manquee.
#
# Le repere de la derniere sauvegarde est ecrit sur le volume de destination :
# il survit au redemarrage du conteneur comme a celui de la machine.
# ============================================================

set -eu

RACINE="${BACKUP_ROOT:-/sauvegardes}"
HEURE_CIBLE="${BACKUP_HOUR:-1}"
LANCER_AU_DEMARRAGE="${BACKUP_ON_START:-0}"
REPERE="$RACINE/.derniere-sauvegarde"
INTERVALLE_CONTROLE=300

journal() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] planificateur : $*"
}

executer_sauvegarde() {
    jour="$1"
    if /usr/local/bin/sauvegarde.sh; then
        echo "$jour" > "$REPERE"
        journal "sauvegarde du $jour enregistrée"
    else
        journal "la sauvegarde a échoué — nouvelle tentative au prochain contrôle"
    fi
}

mkdir -p "$RACINE" 2>/dev/null || true

journal "démarré — sauvegarde quotidienne à partir de ${HEURE_CIBLE}h00, destination $RACINE"
if [ -f "$REPERE" ]; then
    journal "dernière sauvegarde enregistrée : $(cat "$REPERE")"
else
    journal "aucune sauvegarde antérieure enregistrée"
fi

if [ "$LANCER_AU_DEMARRAGE" = "1" ]; then
    journal "sauvegarde immédiate demandée au démarrage"
    executer_sauvegarde "$(date +%F)"
fi

while true; do
    aujourdhui="$(date +%F)"
    heure="$(date +%H)"
    derniere="$(cat "$REPERE" 2>/dev/null || echo "")"

    # `10#` force la base decimale : sans cela « 08 » et « 09 » seraient lus
    # comme des nombres octaux invalides et la boucle s'arreterait.
    if [ "$derniere" != "$aujourdhui" ] && [ "$(( 10#$heure ))" -ge "$(( 10#$HEURE_CIBLE ))" ]; then
        if [ -n "$derniere" ] && [ "$(( 10#$heure ))" -gt "$(( 10#$HEURE_CIBLE ))" ]; then
            journal "sauvegarde de ${HEURE_CIBLE}h non effectuée (machine éteinte ou en veille) : rattrapage"
        fi
        executer_sauvegarde "$aujourdhui"
    fi

    sleep "$INTERVALLE_CONTROLE"
done
