"""Annuaire reel de la Direction Generale de l'Enseignement Superieur.

Transcription de l'etat du personnel fourni par la DGES. Ce fichier est la
source unique : la commande `importer_annuaire` s'en sert pour creer les
services et les comptes, et rien n'y est saisi a la main ailleurs.

Conventions retenues avec la DGES :

- **identifiant** : initiale du premier prenom suivie du nom de famille, en
  minuscules et sans accent. Court a saisir chaque matin, stable si l'adresse
  personnelle change, et sans les trois anomalies que portaient les adresses
  fournies — une adresse sans domaine complet, une autre avec une espace, une
  troisieme avec un accent ;
- **role** : il suit la fonction reellement exercee et non l'intitule
  administratif. Les six « charges d'etudes » ne recoivent donc pas tous le
  role Agent d'etude, qui ouvre la saisie et la validation des diplomes :
  seuls les trois du Service Validation Diplome l'obtiennent.

Le nom de famille est en capitales dans le document d'origine ; il est repris
ici tel quel dans `nom`, les prenoms allant dans `prenom`.
"""

from .constants import (
    ROLE_ADMINISTRATEUR,
    ROLE_AGENT,
    ROLE_AGENT_ETUDE,
    ROLE_COURRIER,
    ROLE_DIRECTEUR_GENERAL,
    ROLE_SECRETARIAT,
    ROLE_SECRETARIAT_ADJOINT,
)

# Services de la DGES, dans l'ordre de l'organigramme.
SERVICES = [
    "Direction Générale",
    "Secrétariat du Directeur Général",
    "Service Courrier",
    "Service Administratif et Financier",
    "Service Validation Diplôme",
    "Service Suivi et Évaluation Projet",
    "Service Communication",
    "Service Informatique",
]

# matricule, nom, prenom, identifiant, fonction, role, service, email
AGENTS = [
    {
        "matricule": "255 853 C",
        "nom": "DOUMBIA",
        "prenom": "Vafi",
        "identifiant": "vdoumbia",
        "fonction": "Professeur titulaire — Directeur Général",
        "role": ROLE_DIRECTEUR_GENERAL,
        "service": "Direction Générale",
        # L'adresse fournie, « vafi@yahoo », n'a pas de domaine complet : elle
        # est laissee vide plutot que d'enregistrer une adresse a laquelle
        # aucun message ne partira jamais.
        "email": "",
        "telephone": "05 54 71 11 11",
    },
    {
        "matricule": "257 665 M",
        "nom": "NGAZA",
        "prenom": "Koua Rémi",
        "identifiant": "kngaza",
        "fonction": "Inspecteur en chef option Anglais — Chargé d'Études",
        "role": ROLE_AGENT,
        "service": "Service Administratif et Financier",
        "email": "reiisnananngaza@gmail.com",
        "telephone": "07 07 63 86 02",
    },
    {
        "matricule": "257 665 M",
        "nom": "KOSSA",
        "prenom": "Gondo",
        "identifiant": "gkossa",
        "fonction": "Inspecteur en chef option orientation — Chargé d'Études",
        "role": ROLE_AGENT,
        "service": "Service Suivi et Évaluation Projet",
        "email": "gondo_kossa@yahoo.fr",
        "telephone": "07 07 60 79 06",
    },
    {
        "matricule": "346 727 C",
        "nom": "KOUTOUAN",
        "prenom": "Marie-Jeanne",
        "identifiant": "mkoutouan",
        "fonction": "Inspecteur en chef option orientation — Chargée d'Études",
        "role": ROLE_AGENT_ETUDE,
        "service": "Service Validation Diplôme",
        "email": "kmari77@gmail.com",
        "telephone": "07 07 37 85 21",
    },
    {
        "matricule": "346 695 D",
        "nom": "KOFFO",
        "prenom": "Eric-Vincent",
        "identifiant": "ekoffo",
        "fonction": "Inspecteur en chef option orientation — Chargé d'Études",
        "role": ROLE_AGENT,
        "service": "Service Communication",
        "email": "koffoericvincent@gmail.com",
        "telephone": "07 58 27 00 01",
    },
    {
        "matricule": "324 295 W",
        "nom": "BOKOLA",
        "prenom": "Zouhoulio Honorine",
        "identifiant": "zbokola",
        "fonction": "Inspecteur orientation — Chargée d'Études",
        "role": ROLE_AGENT_ETUDE,
        "service": "Service Validation Diplôme",
        # L'adresse fournie contenait une espace : « Honorine bokola@gmail.com ».
        "email": "honorinebokola@gmail.com",
        "telephone": "07 07 38 76 44",
    },
    {
        "matricule": "283 266 G",
        "nom": "DOSSO",
        "prenom": "Siafa",
        "identifiant": "sdosso",
        "fonction": "Éducateur — Chargé d'Études",
        "role": ROLE_AGENT_ETUDE,
        "service": "Service Validation Diplôme",
        "email": "siafadosso@gmail.com",
        "telephone": "07 08 81 92 66",
    },
    {
        "matricule": "246 810 G",
        "nom": "GABALA",
        "prenom": "Esther Alice",
        "identifiant": "egabala",
        "fonction": "Secrétaire de direction — Assistante du DG",
        "role": ROLE_SECRETARIAT,
        "service": "Secrétariat du Directeur Général",
        # L'adresse fournie portait un accent : « secrétariat@gmail.com ».
        "email": "secretariat@gmail.com",
        "telephone": "07 07 57 79 71",
    },
    {
        "matricule": "470 467 H",
        "nom": "KOAKOU",
        "prenom": "Kouadio Athanase",
        "identifiant": "kkoakou",
        "fonction": "Adjoint Administratif — Service courrier",
        "role": ROLE_COURRIER,
        "service": "Service Courrier",
        "email": "kkouadioathanase@gmail.com",
        "telephone": "07 57 90 02 38",
    },
    {
        "matricule": "908 873 B",
        "nom": "SILUE",
        "prenom": "Nanougoué Prince",
        "identifiant": "nsilue",
        "fonction": "Agent de maîtrise TP — Chauffeur du DG",
        "role": ROLE_AGENT,
        # « Chauffeur » n'est pas un service : le rattacher a la Direction
        # Generale evite un service d'une seule personne dans les listes
        # d'imputation du courrier.
        "service": "Direction Générale",
        "email": "princesiluedges@gmail.com",
        "telephone": "01 01 35 06 63",
    },
    {
        "matricule": "877 209 K",
        "nom": "N'CHO",
        "prenom": "Assi Serges Landry",
        "identifiant": "ancho",
        "fonction": "Adjoint Administratif — Service courrier",
        "role": ROLE_COURRIER,
        "service": "Service Courrier",
        "email": "assisergencho@gmail.com",
        "telephone": "07 07 26 70 14",
    },
    {
        "matricule": "FNCE24-0211145",
        "nom": "GRAH",
        "prenom": "Yotcho Ange Augustin",
        "identifiant": "agrah",
        "fonction": "Ingénieur informaticien option Génie Logiciel — Gestion informatique",
        "role": ROLE_ADMINISTRATEUR,
        "service": "Service Informatique",
        "email": "grahaugustin@gmail.com",
        "telephone": "01 01 67 40 23",
    },
    {
        "matricule": "246 810 G",
        "nom": "DIABATE",
        "prenom": "Tiantio Mariette",
        "identifiant": "tdiabate",
        "fonction": "Conseiller d'orientation — Chargé d'Études",
        "role": ROLE_AGENT,
        "service": "Service Administratif et Financier",
        "email": "diabatetiantio@gmail.com",
        "telephone": "01 01 15 44 30",
    },
    {
        "matricule": "891629 W",
        "nom": "KOUADIO",
        "prenom": "Akissi Catherine",
        "identifiant": "akouadio",
        "fonction": "Secrétaire de direction — Assistante du DG",
        "role": ROLE_SECRETARIAT_ADJOINT,
        "service": "Secrétariat du Directeur Général",
        "email": "kouadioakissicatherine@gmail.com",
        "telephone": "07 77 10 06 19",
    },
]

# Responsables de service, designes par leur identifiant.
RESPONSABLES = {
    "Direction Générale": "vdoumbia",
    "Secrétariat du Directeur Général": "egabala",
    "Service Courrier": "kkoakou",
    "Service Validation Diplôme": "mkoutouan",
    "Service Informatique": "agrah",
}
