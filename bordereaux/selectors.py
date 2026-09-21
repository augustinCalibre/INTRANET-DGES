"""Lectures du suivi des bordereaux.

Les comptages traduisent en SQL la meme regle que `Bordereau.etat` : un
dossier dont la liquidation est signee est termine, un dossier engage mais
non liquide est en cours, le reste attend son engagement. Les trois
conditions ci-dessous sont l'unique endroit ou cette traduction est ecrite.
"""

from django.db.models import Case, CharField, Count, F, IntegerField, Q, Value, When

from core.permissions import can_access_bordereaux

from .models import Bordereau, Organisme, Trimestre

# Traduction SQL des trois etats. Elles s'excluent et couvrent tous les cas :
# leur somme vaut toujours le nombre de bordereaux de la periode.
Q_TERMINE = Q(date_liquidation__isnull=False)
Q_EN_COURS = Q(date_liquidation__isnull=True, date_engagement__isnull=False)
Q_ATTENTE = Q(date_liquidation__isnull=True, date_engagement__isnull=True)

FILTRES_PAR_ETAT = {
    Bordereau.Etat.TERMINE: Q_TERMINE,
    Bordereau.Etat.EN_COURS: Q_EN_COURS,
    Bordereau.Etat.ATTENTE_ENGAGEMENT: Q_ATTENTE,
}

COMPTEURS = {
    "total": Count("id"),
    "termines": Count("id", filter=Q_TERMINE),
    "en_cours": Count("id", filter=Q_EN_COURS),
    "attente": Count("id", filter=Q_ATTENTE),
}


def libelle_de_tri():
    """Le sigle, ou le nom quand aucun sigle n'est renseigne.

    C'est la cle de tri des organismes : elle suit ce que l'ecran montre.
    Sans le repli sur le nom, un organisme sans sigle remonterait en tete de
    liste, la chaine vide precedant toutes les autres.
    """
    return Case(
        When(sigle="", then=F("nom")),
        default=F("sigle"),
        output_field=CharField(),
    )


def get_bordereaux_scope(user):
    """Bordereaux accessibles a ce compte.

    Le suivi est un registre de direction : il se lit en entier ou pas du
    tout. Aucun decoupage par service ne s'y applique.
    """
    if not getattr(user, "is_authenticated", False) or not can_access_bordereaux(user):
        return Bordereau.objects.none()
    return Bordereau.objects.select_related("organisme")


def filtrer_par_etat(queryset, etat):
    """Restreint aux bordereaux dans cet etat, sans toucher au queryset sinon."""
    condition = FILTRES_PAR_ETAT.get(etat)
    return queryset.filter(condition) if condition else queryset


def get_annees_suivies(user):
    """Annees ou un bordereau a ete enregistre, de la plus recente a la plus ancienne."""
    return list(
        get_bordereaux_scope(user)
        .values_list("annee", flat=True)
        .order_by("-annee")
        .distinct()
    )


def get_organismes(actifs_seulement=True):
    queryset = Organisme.objects.all()
    if actifs_seulement:
        queryset = queryset.filter(actif=True)
    # L'agregation pose un GROUP BY : Django considere alors le queryset comme
    # non ordonne. On reprend l'ordre explicitement pour que la pagination
    # reste stable d'une page a l'autre.
    #
    # Et on trie sur ce que le tableau affiche, c'est-a-dire le sigle : classer
    # « Prise en charge » d'apres son nom complet le placerait entre DEXCO et
    # GPE, a un endroit ou personne ne le cherche.
    return (
        queryset.annotate(
            nb_bordereaux=Count("bordereaux"),
            libelle_tri=libelle_de_tri(),
        )
        .order_by("libelle_tri", "nom")
    )


def get_compteurs_periode(user, annee, trimestre=None, organisme=None):
    """Repartition par etat sur une periode, eventuellement pour un organisme."""
    queryset = get_bordereaux_scope(user).filter(annee=annee)
    if trimestre:
        queryset = queryset.filter(trimestre=trimestre)
    if organisme:
        queryset = queryset.filter(organisme=organisme)
    compteurs = queryset.aggregate(**COMPTEURS)
    return {cle: compteurs.get(cle) or 0 for cle in COMPTEURS}


def get_tableau_annuel(user, annee, organismes):
    """Grille Organisme -> quatre boites trimestrielles, pour une annee.

    Un seul passage en base : les comptages sont agreges par couple
    (organisme, trimestre), puis redistribues en Python. La grille reste
    complete meme pour un organisme sans aucun bordereau cette annee-la,
    afin que ses boites vides restent cliquables pour une premiere saisie.
    """
    organismes = list(organismes)
    agregats = {
        (ligne["organisme_id"], ligne["trimestre"]): ligne
        for ligne in get_bordereaux_scope(user)
        .filter(annee=annee, organisme__in=organismes)
        .values("organisme_id", "trimestre")
        .annotate(**COMPTEURS)
    }

    lignes = []
    for organisme in organismes:
        boites = []
        for trimestre in Trimestre:
            agregat = agregats.get((organisme.pk, trimestre.value), {})
            boites.append(
                {
                    "trimestre": trimestre.value,
                    "label": trimestre.label,
                    "total": agregat.get("total", 0),
                    "termines": agregat.get("termines", 0),
                    "en_cours": agregat.get("en_cours", 0),
                    "attente": agregat.get("attente", 0),
                }
            )
        lignes.append(
            {
                "organisme": organisme,
                "boites": boites,
                "total": sum(boite["total"] for boite in boites),
            }
        )
    return lignes


def get_bordereaux_de_la_boite(user, annee, trimestre, organisme):
    return (
        get_bordereaux_scope(user)
        .filter(annee=annee, trimestre=trimestre, organisme=organisme)
        # Un dossier pas encore numerote se lit mal au milieu d'une suite de
        # numeros — et la chaine vide le placerait justement en tete. On
        # regroupe ces dossiers en fin de boite, par date de reception.
        .annotate(
            sans_numero=Case(
                When(numero="", then=Value(1)),
                default=Value(0),
                output_field=IntegerField(),
            )
        )
        .order_by("sans_numero", "numero", "date_reception")
    )


def get_bordereaux_en_attente(user):
    """Dossiers dont l'engagement n'est toujours pas signe : le badge du menu."""
    return get_bordereaux_scope(user).filter(Q_ATTENTE)
