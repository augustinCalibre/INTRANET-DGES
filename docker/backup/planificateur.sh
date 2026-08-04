#!/bin/sh
# ============================================================
# Planificateur et executant du service de sauvegarde
#
# Deux responsabilites, une seule boucle :
#
#   1. La sauvegarde quotidienne. On verifie l'heure reelle toutes les cinq
#      secondes et on sauvegarde des qu'un nouveau jour est entame et que
#      l'heure cible est passee.
#
#      Pourquoi pas un simple « dormir jusqu'a 1h00 » : quand la machine se met
#      en veille, le conteneur est gele et le compte a rebours s'arrete avec
#      lui. Au reveil il resterait des heures a attendre, et la sauvegarde de
#      la nuit serait perdue. Ici, un poste rallume a 8h00 rattrape la
#      sauvegarde manquee.
#
#   2. Les demandes de l'application. L'intranet ne peut ni sauvegarder ni
#      restaurer lui-meme : il n'a ni pg_dump, ni le droit de detruire la base
#      a laquelle il est connecte. Il depose donc un fichier de demande dans un
#      volume partage, que ce service execute.
#
#      Ce detour vaut mieux que l'alternative — donner au conteneur web l'acces
#      au socket Docker — qui reviendrait a confier a une application web le
#      pouvoir d'arreter et de recreer n'importe quel conteneur de la machine.
#
# Le repere de la derniere sauvegarde est ecrit sur le volume de destination :
# il survit au redemarrage du conteneur comme a celui de la machine.
# ============================================================

set -u

RACINE="${BACKUP_ROOT:-/sauvegardes}"
CONTROLE="${BACKUP_CONTROL_DIR:-/controle}"
HEURE_CIBLE="${BACKUP_HOUR:-1}"
LANCER_AU_DEMARRAGE="${BACKUP_ON_START:-0}"
REPERE="$RACINE/.derniere-sauvegarde"
DEMANDE="$CONTROLE/demande"
INTERVALLE_CONTROLE=5

journal() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] planificateur : $*"
}

# Etat courant, lu par l'application pour afficher l'avancement. Voir
# restauration.sh pour le choix du format « cle=valeur ».
etat() {
    {
        echo "operation=sauvegarde"
        echo "archive="
        echo "etape=$1"
        echo "message=$2"
        echo "horodatage=$(date '+%Y-%m-%d %H:%M:%S')"
        echo "demandeur=${DEMANDEUR:-}"
    } > "$CONTROLE/etat.tmp" 2>/dev/null || return 0
    mv "$CONTROLE/etat.tmp" "$CONTROLE/etat" 2>/dev/null || true
}

historique() {
    printf '%s|sauvegarde|%s|%s|%s\n' \
        "$(date '+%Y-%m-%d %H:%M:%S')" "$1" "$2" "${DEMANDEUR:-}" \
        >> "$CONTROLE/journal.txt" 2>/dev/null || true
}

executer_sauvegarde() {
    jour="$1"
    etat "en_cours" "Sauvegarde en cours"
    if /usr/local/bin/sauvegarde.sh; then
        [ -n "$jour" ] && echo "$jour" > "$REPERE"
        derniere_archive="$(ls -1t "$RACINE"/sauvegarde_*.zip 2>/dev/null | head -1)"
        etat "termine" "Sauvegarde terminée"
        historique "$(basename "${derniere_archive:-}")" "succes"
        journal "sauvegarde enregistrée"
        return 0
    fi
    etat "echec" "La sauvegarde a échoué, voir les journaux du service"
    historique "" "echec"
    journal "la sauvegarde a échoué"
    return 1
}

lire_champ() {
    sed -n "s/^$1=//p" "$DEMANDE" 2>/dev/null | head -1
}

traiter_demande() {
    action="$(lire_champ action)"
    archive="$(lire_champ archive)"
    DEMANDEUR="$(lire_champ demandeur)"
    export DEMANDEUR

    # La demande est consommee avant d'etre executee. Si l'operation echoue,
    # elle ne doit pas etre rejouee en boucle a chaque tour.
    rm -f "$DEMANDE"

    case "$action" in
        sauvegarde)
            journal "sauvegarde demandée par ${DEMANDEUR:-un administrateur}"
            executer_sauvegarde ""
            ;;
        restauration)
            journal "restauration demandée par ${DEMANDEUR:-un administrateur} depuis $archive"
            /usr/local/bin/restauration.sh "$archive" || true
            ;;
        *)
            journal "demande ignorée, action inconnue : $action"
            ;;
    esac

    DEMANDEUR=""
}

mkdir -p "$RACINE" 2>/dev/null || true
mkdir -p "$CONTROLE" 2>/dev/null || true

# Un mode maintenance laisse par une restauration interrompue — machine
# eteinte en plein travail — condamnerait l'application au redemarrage. On le
# leve, quitte a ce que l'etat affiche reste sur un echec.
if [ -f "$CONTROLE/maintenance" ]; then
    journal "mode maintenance résiduel détecté, levée automatique"
    rm -f "$CONTROLE/maintenance"
fi
rm -f "$DEMANDE" 2>/dev/null || true

DEMANDEUR=""

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
    if [ -f "$DEMANDE" ]; then
        traiter_demande
    fi

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
