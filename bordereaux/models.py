"""Suivi trimestriel des bordereaux presentes au circuit de signature.

Le module trace les signatures, pas l'argent : aucun montant financier n'est
conserve, seulement des numeros de bordereaux, des dates et l'etat
d'avancement du dossier.

Deux partis pris structurent ce fichier.

L'etat d'un bordereau n'est pas un champ. Il se deduit des dates de signature
deja saisies (`Bordereau.etat`), et les comptages l'expriment en SQL par les
memes conditions (`bordereaux.selectors`). Un statut stocke finirait tot ou
tard en desaccord avec les dates ; ici la question ne se pose pas.

Le mandat n'a pas de date de signature. La regle metier retenue veut qu'une
liquidation signee prouve le passage du Controleur financier : exiger une
saisie separee du mandat ne ferait que retarder la cloture d'un dossier deja
termine. Le mandat est donc signale « validé par déduction » des que la
liquidation est signee.
"""

from pathlib import Path
from uuid import uuid4

from django.contrib.auth.models import User
from django.db import models
from django.utils import timezone
from django.utils.text import slugify


class Organisme(models.Model):
    """Etablissement ou structure dont les bordereaux passent au visa."""

    nom = models.CharField(max_length=180, unique=True)
    sigle = models.CharField(
        max_length=30,
        blank=True,
        help_text="Abréviation utilisée dans le tableau de suivi, par exemple UFHB.",
    )
    actif = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["nom"]
        verbose_name = "Organisme"
        verbose_name_plural = "Organismes"

    def __str__(self):
        return self.sigle or self.nom

    @property
    def libelle_court(self):
        """Le sigle quand il existe : c'est lui qui tient dans une boite."""
        return self.sigle or self.nom

    @property
    def libelle_complet(self):
        if self.sigle and self.sigle != self.nom:
            return f"{self.sigle} — {self.nom}"
        return self.nom


class Trimestre(models.IntegerChoices):
    T1 = 1, "T1"
    T2 = 2, "T2"
    T3 = 3, "T3"
    T4 = 4, "T4"


TRIMESTRE_PERIODES = {
    Trimestre.T1: "Janvier - Mars",
    Trimestre.T2: "Avril - Juin",
    Trimestre.T3: "Juillet - Septembre",
    Trimestre.T4: "Octobre - Décembre",
}


def trimestre_de(date):
    """Trimestre calendaire auquel appartient une date."""
    return Trimestre((date.month - 1) // 3 + 1)


def bordereau_upload_path(instance, filename):
    """Range la piece par annee, sous un nom qui ne peut pas en ecraser un autre."""
    original = Path(filename)
    base = slugify(original.stem) or "bordereau"
    annee = instance.annee or timezone.localdate().year
    return f"bordereaux/{annee}/{base}-{uuid4().hex[:12]}{original.suffix.lower()}"


class Bordereau(models.Model):
    class Etat(models.TextChoices):
        ATTENTE_ENGAGEMENT = "attente_engagement", "Engagement en attente"
        EN_COURS = "en_cours", "En cours"
        TERMINE = "termine", "Terminé"

    # Ordre d'avancement, du dossier qui vient d'arriver a celui qui est clos.
    ETATS_ORDONNES = [Etat.ATTENTE_ENGAGEMENT, Etat.EN_COURS, Etat.TERMINE]

    organisme = models.ForeignKey(
        Organisme,
        on_delete=models.PROTECT,
        related_name="bordereaux",
        verbose_name="Organisme",
    )
    annee = models.PositiveIntegerField(verbose_name="Année")
    trimestre = models.PositiveSmallIntegerField(choices=Trimestre.choices)
    # Le numero n'est pas toujours connu a la reception : il arrive que le
    # bordereau soit enregistre d'abord et numerote ensuite. Le dossier existe
    # quand meme, et se designe alors par sa date de reception.
    numero = models.CharField(
        max_length=60,
        blank=True,
        verbose_name="N° de bordereau",
    )
    date_reception = models.DateField(
        default=timezone.localdate,
        verbose_name="Date de réception",
    )
    # Le bordereau lui-meme, scanne ou tel qu'il a ete transmis. Il reste la
    # piece de reference : c'est lui qu'on rouvre quand une date est contestee.
    fichier = models.FileField(
        upload_to=bordereau_upload_path,
        blank=True,
        verbose_name="Bordereau",
    )
    date_engagement = models.DateField(
        null=True,
        blank=True,
        verbose_name="Signature de l'engagement",
    )
    date_liquidation = models.DateField(
        null=True,
        blank=True,
        verbose_name="Signature de la liquidation",
    )
    observation = models.TextField(blank=True)
    cree_par = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="bordereaux_crees",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-annee", "trimestre", "organisme__nom", "numero", "date_reception"]
        verbose_name = "Bordereau"
        verbose_name_plural = "Bordereaux"
        constraints = [
            # Un meme numero ne se represente pas deux fois dans l'annee pour un
            # organisme donne : c'est une saisie en double, pas un nouveau
            # dossier. La contrainte ignore volontairement le trimestre, sans
            # quoi le doublon passerait en changeant de boite.
            #
            # Elle ne s'applique qu'aux bordereaux numerotes : plusieurs
            # dossiers peuvent attendre leur numero en meme temps, et les
            # exclure les uns les autres n'aurait aucun sens.
            models.UniqueConstraint(
                fields=["organisme", "annee", "numero"],
                condition=~models.Q(numero=""),
                name="unique_numero_bordereau_par_annee",
            )
        ]
        indexes = [
            models.Index(fields=["annee", "trimestre"], name="bord_periode_idx"),
            models.Index(fields=["numero"], name="bord_numero_idx"),
            models.Index(fields=["-date_reception"], name="bord_reception_idx"),
        ]

    def __str__(self):
        return f"{self.libelle} - {self.organisme.libelle_court} ({self.periode_label})"

    # -- Designation ---------------------------------------------------

    @property
    def est_numerote(self):
        return bool(self.numero)

    @property
    def libelle(self):
        """Comment designer ce bordereau partout ou son numero est attendu.

        Un dossier enregistre avant d'etre numerote se reconnait a sa date de
        reception : c'est ce que dit l'agent qui le cherche (« celui du 5 »).
        """
        if self.numero:
            return self.numero
        if self.date_reception:
            return f"Sans numéro · reçu le {self.date_reception:%d/%m/%Y}"
        return "Sans numéro"

    # -- Piece jointe --------------------------------------------------

    @property
    def nom_fichier(self):
        return Path(self.fichier.name).name if self.fichier else ""

    @property
    def fichier_est_pdf(self):
        """Un PDF s'affiche dans la fiche ; tout le reste se telecharge."""
        return self.nom_fichier.lower().endswith(".pdf")

    # -- Lecture de l'avancement ---------------------------------------

    @property
    def engagement_signe(self):
        return self.date_engagement is not None

    @property
    def liquidation_signee(self):
        return self.date_liquidation is not None

    @property
    def mandat_deduit(self):
        """Le Controleur financier a valide, puisque la liquidation est signee."""
        return self.liquidation_signee

    @property
    def etat(self):
        if self.liquidation_signee:
            return self.Etat.TERMINE
        if self.engagement_signe:
            return self.Etat.EN_COURS
        return self.Etat.ATTENTE_ENGAGEMENT

    @property
    def etat_label(self):
        return self.Etat(self.etat).label

    @property
    def etat_badge_class(self):
        return {
            self.Etat.ATTENTE_ENGAGEMENT: "badge bordereau-etat-attente",
            self.Etat.EN_COURS: "badge bordereau-etat-encours",
            self.Etat.TERMINE: "badge bordereau-etat-termine",
        }[self.etat]

    @property
    def est_termine(self):
        return self.etat == self.Etat.TERMINE

    @property
    def etape_index(self):
        """Rang de l'etape atteinte, de 1 (engagement attendu) a 3 (clos)."""
        return self.ETATS_ORDONNES.index(self.etat) + 1

    @property
    def mandat_label(self):
        return "Validé par déduction" if self.mandat_deduit else "Non déduit"

    @property
    def periode_label(self):
        return f"{self.get_trimestre_display()} {self.annee}"

    @property
    def periode_detail(self):
        return TRIMESTRE_PERIODES.get(Trimestre(self.trimestre), "")

    @property
    def delai_traitement(self):
        """Jours ecoules entre la reception et la signature qui clot le circuit."""
        if not self.liquidation_signee or not self.date_reception:
            return None
        return (self.date_liquidation - self.date_reception).days


class BordereauHistory(models.Model):
    bordereau = models.ForeignKey(
        Bordereau,
        on_delete=models.CASCADE,
        related_name="historiques",
    )
    action = models.CharField(max_length=180)
    ancien_etat = models.CharField(max_length=30, blank=True)
    nouvel_etat = models.CharField(max_length=30, blank=True)
    commentaire = models.TextField(blank=True)
    utilisateur = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="bordereau_histories",
    )
    date = models.DateTimeField(auto_now_add=True)

    class Meta:
        # `-id` departage deux mouvements enregistres dans la meme seconde :
        # signer l'engagement puis la liquidation coup sur coup les afficherait
        # sinon dans un ordre indetermine, la cloture avant son ouverture.
        ordering = ["-date", "-id"]
        verbose_name = "Historique de bordereau"
        verbose_name_plural = "Historiques de bordereau"

    def __str__(self):
        return f"{self.bordereau.numero} - {self.action}"
