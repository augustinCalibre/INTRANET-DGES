"""Mise en forme des donnees pour les visualisations du tableau de bord.

Les barres du tableau de bord sont rendues en HTML et CSS : pas de
bibliotheque de graphiques, donc aucune dependance externe a charger, ce qui
reste compatible avec la politique de securite du contenu servie par Nginx.

Choix de representation, dans l'ordre impose par la methode :

1. Forme. Comparer des grandeurs -> barres horizontales. Les chiffres de tete
   ne sont pas des graphiques mais des tuiles. Les files d'attente de decision
   sont des listes, pas des graphiques.
2. Couleur. Une seule teinte. Les etapes d'un circuit forment une echelle
   ordonnee : la rampe s'assombrit avec l'avancement. Aucune palette
   categorielle, donc aucun risque de confusion pour un lecteur daltonien.
3. Validation. Les rampes ont ete verifiees contre les surfaces reelles de
   l'application (#ffffff en clair, #111f2d en sombre) : teinte unique,
   luminosite monotone, ecarts de pas suffisants, extremite claire au-dessus
   du seuil de 2:1. Voir `static/css/dashboard-viz.css`.
"""

RAMP_STEPS = 5


def build_distribution(rows, base_url, param="statut"):
    """Transforme des comptages ordonnes en barres horizontales.

    `rows` est une liste de dictionnaires {key, label, total}, dans l'ordre du
    circuit. Chaque barre recoit sa largeur relative au maximum observe et son
    pas dans la rampe, qui suit l'avancement dans le circuit.
    """
    rows = list(rows)
    if not rows:
        return []

    maximum = max(item["total"] for item in rows) or 1
    total = sum(item["total"] for item in rows)
    dernier = max(1, len(rows) - 1)

    distribution = []
    for index, item in enumerate(rows):
        # Une barre a zero reste visible sous forme de trait : l'absence est une
        # information, pas un vide.
        largeur = round(item["total"] * 100 / maximum) if item["total"] else 0
        distribution.append(
            {
                "key": item["key"],
                "label": item["label"],
                "total": item["total"],
                "largeur": max(largeur, 1) if item["total"] else 0,
                "part": round(item["total"] * 100 / total) if total else 0,
                "step": round(index * (RAMP_STEPS - 1) / dernier),
                "url": f"{base_url}?{param}={item['key']}",
            }
        )
    return distribution


def build_service_load(services):
    """Charge par service : une mesure unique, comparee entre services.

    On ne cumule pas des grandeurs de nature differente dans une meme barre :
    additionner des courriers et des visiteurs ne voudrait rien dire. La barre
    porte les taches ouvertes, les autres colonnes restent des nombres.
    """
    services = list(services)
    if not services:
        return []

    maximum = max(service.taches_ouvertes for service in services) or 1
    return [
        {
            "service": service,
            "largeur": round(service.taches_ouvertes * 100 / maximum)
            if service.taches_ouvertes
            else 0,
        }
        for service in services
    ]
