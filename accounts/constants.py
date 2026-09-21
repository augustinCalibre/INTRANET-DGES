"""Roles de la DGES et matrice de droits.

Un seul fichier decrit qui est qui et qui peut quoi. Les vues et les
selectors n'interrogent jamais un role directement : ils passent par les
capacites exposees dans `core.permissions`, construites a partir des
ensembles definis ici. Ajouter un role revient donc a l'inscrire dans un
ou plusieurs ensembles, sans toucher au reste du code.
"""

ROLE_DIRECTEUR_GENERAL = "directeur_general"
ROLE_ADMINISTRATEUR = "administrateur"
ROLE_SECRETARIAT = "secretariat"
ROLE_SECRETARIAT_ADJOINT = "secretariat_adjoint"
ROLE_COURRIER = "courrier"
ROLE_AGENT_ETUDE = "agent_etude"
ROLE_AGENT = "agent"

ROLE_CHOICES = [
    (ROLE_DIRECTEUR_GENERAL, "Directeur Général"),
    (ROLE_ADMINISTRATEUR, "Administrateur"),
    (ROLE_SECRETARIAT, "Secrétariat"),
    (ROLE_SECRETARIAT_ADJOINT, "Secrétariat adjoint"),
    (ROLE_COURRIER, "Service courrier"),
    (ROLE_AGENT_ETUDE, "Agent d'étude / vérificateur"),
    (ROLE_AGENT, "Agent"),
]

ROLE_GROUP_NAMES = {
    ROLE_DIRECTEUR_GENERAL: "DGES - Directeur Général",
    ROLE_ADMINISTRATEUR: "DGES - Administrateur",
    ROLE_SECRETARIAT: "DGES - Secrétariat",
    ROLE_SECRETARIAT_ADJOINT: "DGES - Secrétariat adjoint",
    ROLE_COURRIER: "DGES - Service courrier",
    ROLE_AGENT_ETUDE: "DGES - Agent d'étude",
    ROLE_AGENT: "DGES - Agent",
}

# Anciens roles, conserves le temps de migrer les comptes existants.
LEGACY_ROLE_MAP = {
    "agent_simple": ROLE_AGENT,
    "responsable_service": ROLE_AGENT,
}

# Groupes de l'ancien modele, supprimes par la migration 0004.
OBSOLETE_GROUP_NAMES = [
    "DGES - Directeur General",
    "DGES - Secretariat",
    "DGES - Responsable service",
    "DGES - Agent simple",
    "DGES - Service Courrier",
]


# ---------------------------------------------------------------------
# Matrice de droits
#
# Regle structurante : rien n'atteint le bureau du Directeur General sans
# le visa du Secretariat. Elle vaut pour les courriers comme pour les
# lots de diplomes.
# ---------------------------------------------------------------------

# Lecture de l'activite de toute la direction, sans restriction de service.
ROLES_VUE_GLOBALE = {
    ROLE_DIRECTEUR_GENERAL,
    ROLE_ADMINISTRATEUR,
}

# Enregistrement des visiteurs et tenue du registre d'entree.
ROLES_VISITEURS = {
    ROLE_SECRETARIAT,
    ROLE_SECRETARIAT_ADJOINT,
    ROLE_ADMINISTRATEUR,
}

# Reception, enregistrement et traitement du courrier.
# Le Secretariat adjoint y figure : il « declenche les courriers ».
ROLES_COURRIER = {
    ROLE_COURRIER,
    ROLE_SECRETARIAT_ADJOINT,
    ROLE_ADMINISTRATEUR,
}

# Depot et classement documentaire au sens large.
ROLES_DOCUMENTS = {
    ROLE_COURRIER,
    ROLE_SECRETARIAT,
    ROLE_SECRETARIAT_ADJOINT,
    ROLE_ADMINISTRATEUR,
}

# Visa du Secretariat : seul point de passage vers le Directeur General.
ROLES_TRANSMISSION_DG = {
    ROLE_SECRETARIAT,
    ROLE_ADMINISTRATEUR,
}

# Validation et signature.
ROLES_VALIDATION_DG = {
    ROLE_DIRECTEUR_GENERAL,
    ROLE_ADMINISTRATEUR,
}

# Classement d'un courrier, une fois la suite donnee. Le Directeur General et
# le Secretariat cloturent l'affaire au meme titre que le service courrier.
ROLES_CLASSEMENT = ROLES_COURRIER | ROLES_TRANSMISSION_DG | ROLES_VALIDATION_DG

# Saisie de la fiche d'analyse : imputations, instructions, observations.
# Le Directeur General annote souvent la fiche papier au moment de la remise ;
# le Secretariat reporte ensuite sa decision dans le systeme. Les deux peuvent
# donc saisir, et l'application conserve qui l'a fait.
ROLES_FICHE_DG = ROLES_VALIDATION_DG | ROLES_TRANSMISSION_DG

# Reception des lots, insertion et verification de chaque diplome.
ROLES_DIPLOMES = {
    ROLE_AGENT_ETUDE,
    ROLE_ADMINISTRATEUR,
}

# Acces au registre du courrier. Le Secretariat vise, le DG traite.
ROLES_ACCES_COURRIERS = ROLES_COURRIER | ROLES_TRANSMISSION_DG | ROLES_VALIDATION_DG

# Acces en lecture au registre des lots. Plus large que ROLES_DIPLOMES :
# le Secretariat doit voir les lots pour les transmettre et le DG pour les
# signer, sans pour autant pouvoir en modifier le contenu.
ROLES_ACCES_DIPLOMES = ROLES_DIPLOMES | ROLES_TRANSMISSION_DG | ROLES_VALIDATION_DG

# Tenue du suivi trimestriel des bordereaux : enregistrement des dossiers
# presentes au circuit de signature et saisie des dates de signature.
# Le Secretariat suit ces bordereaux comme il suit les parapheurs ; le
# module ne conserve aucun montant, seulement des numeros et des dates.
ROLES_BORDEREAUX = {
    ROLE_SECRETARIAT,
    ROLE_SECRETARIAT_ADJOINT,
    ROLE_ADMINISTRATEUR,
}

# Lecture du tableau de suivi. Le Directeur General consulte l'avancement
# des dossiers sans saisir lui-meme les signatures.
ROLES_ACCES_BORDEREAUX = ROLES_BORDEREAUX | ROLES_VALIDATION_DG

# Planning du Directeur General et reunions de toute la direction.
ROLES_PLANNING = {
    ROLE_SECRETARIAT,
    ROLE_SECRETARIAT_ADJOINT,
    ROLE_ADMINISTRATEUR,
}

# Affectation d'une tache a un autre agent ou a un autre service.
ROLES_AFFECTATION_LIBRE = {
    ROLE_DIRECTEUR_GENERAL,
    ROLE_ADMINISTRATEUR,
    ROLE_SECRETARIAT,
    ROLE_SECRETARIAT_ADJOINT,
}

# Creation des comptes et distribution des acces.
ROLES_GESTION_COMPTES = {
    ROLE_ADMINISTRATEUR,
}

# Consultation de l'annuaire des comptes.
ROLES_CONSULTATION_COMPTES = {
    ROLE_ADMINISTRATEUR,
    ROLE_DIRECTEUR_GENERAL,
}

# Sauvegarde et restauration de la plateforme.
#
# Ce role seul, et deliberement. Restaurer une ancienne sauvegarde efface le
# travail saisi depuis : c'est un acte d'exploitation informatique, pas une
# decision administrative. Le Directeur General en est ecarte comme les
# autres — il demande la restauration, l'ingenieur l'execute.
ROLES_SAUVEGARDE = {
    ROLE_ADMINISTRATEUR,
}


# ---------------------------------------------------------------------
# Permissions Django par groupe
#
# Elles gouvernent l'acces a l'administration Django, pas les vues de
# l'application, qui reposent sur les capacites ci-dessus. L'objectif est
# qu'un compte n'y voie que ce qui releve de sa fonction.
# ---------------------------------------------------------------------

_LECTURE_COMMUNE = [
    ("accounts", "view_service"),
    ("accounts", "view_userprofile"),
]

_TACHES_COMPLETES = [
    ("tasks", "view_task"),
    ("tasks", "add_task"),
    ("tasks", "change_task"),
    ("tasks", "view_taskhistory"),
]

GROUP_PERMISSIONS = {
    # Le DG consulte tout et valide ; il ne saisit pas.
    ROLE_DIRECTEUR_GENERAL: _LECTURE_COMMUNE
    + _TACHES_COMPLETES
    + [
        ("auth", "view_user"),
        ("visitors", "view_visitor"),
        ("documents", "view_document"),
        ("documents", "change_document"),
        ("meetings", "view_meeting"),
        ("diplomas", "view_lotdiplomes"),
        ("diplomas", "change_lotdiplomes"),
        ("diplomas", "view_diplome"),
        ("diplomas", "view_lothistory"),
        ("diplomas", "view_diplomehistory"),
        ("bordereaux", "view_organisme"),
        ("bordereaux", "view_bordereau"),
        ("bordereaux", "view_bordereauhistory"),
        ("core", "view_activitylog"),
        ("core", "view_notification"),
    ],
    # L'administrateur recoit l'integralite des permissions (cf. access.py).
    ROLE_ADMINISTRATEUR: [],
    # Le Secretariat vise, transmet et tient le planning.
    ROLE_SECRETARIAT: _LECTURE_COMMUNE
    + _TACHES_COMPLETES
    + [
        ("auth", "view_user"),
        ("visitors", "view_visitor"),
        ("visitors", "add_visitor"),
        ("visitors", "change_visitor"),
        ("documents", "view_document"),
        ("documents", "add_document"),
        ("documents", "change_document"),
        ("meetings", "view_meeting"),
        ("meetings", "add_meeting"),
        ("meetings", "change_meeting"),
        ("diplomas", "view_lotdiplomes"),
        ("diplomas", "change_lotdiplomes"),
        ("diplomas", "view_diplome"),
        ("bordereaux", "view_organisme"),
        ("bordereaux", "add_organisme"),
        ("bordereaux", "change_organisme"),
        ("bordereaux", "view_bordereau"),
        ("bordereaux", "add_bordereau"),
        ("bordereaux", "change_bordereau"),
        ("bordereaux", "view_bordereauhistory"),
        ("core", "view_activitylog"),
    ],
    # Le Secretariat adjoint enregistre : visiteurs, courriers, planning.
    ROLE_SECRETARIAT_ADJOINT: _LECTURE_COMMUNE
    + _TACHES_COMPLETES
    + [
        ("visitors", "view_visitor"),
        ("visitors", "add_visitor"),
        ("visitors", "change_visitor"),
        ("documents", "view_document"),
        ("documents", "add_document"),
        ("documents", "change_document"),
        ("meetings", "view_meeting"),
        ("meetings", "add_meeting"),
        ("meetings", "change_meeting"),
        ("bordereaux", "view_organisme"),
        ("bordereaux", "add_organisme"),
        ("bordereaux", "change_organisme"),
        ("bordereaux", "view_bordereau"),
        ("bordereaux", "add_bordereau"),
        ("bordereaux", "change_bordereau"),
        ("bordereaux", "view_bordereauhistory"),
    ],
    # Le Service courrier receptionne et traite, sans acces au planning.
    ROLE_COURRIER: _LECTURE_COMMUNE
    + _TACHES_COMPLETES
    + [
        ("documents", "view_document"),
        ("documents", "add_document"),
        ("documents", "change_document"),
        ("meetings", "view_meeting"),
    ],
    # L'agent d'etude travaille sur les lots et les diplomes.
    ROLE_AGENT_ETUDE: _LECTURE_COMMUNE
    + _TACHES_COMPLETES
    + [
        ("documents", "view_document"),
        ("meetings", "view_meeting"),
        ("diplomas", "view_lotdiplomes"),
        ("diplomas", "add_lotdiplomes"),
        ("diplomas", "change_lotdiplomes"),
        ("diplomas", "view_diplome"),
        ("diplomas", "add_diplome"),
        ("diplomas", "change_diplome"),
        ("diplomas", "view_lothistory"),
        ("diplomas", "view_diplomehistory"),
    ],
    # Role par defaut : ses propres taches et la documentation partagee.
    ROLE_AGENT: _LECTURE_COMMUNE
    + _TACHES_COMPLETES
    + [
        ("documents", "view_document"),
        ("meetings", "view_meeting"),
    ],
}
