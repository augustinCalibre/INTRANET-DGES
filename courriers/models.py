from pathlib import Path
from uuid import uuid4

from django.contrib.auth.models import User
from django.db import IntegrityError, models, transaction
from django.utils import timezone
from django.utils.text import slugify

from accounts.models import Service

REFERENCE_PREFIX = "COUR"


def courrier_upload_path(instance, filename):
    original = Path(filename)
    base = slugify(original.stem) or "courrier"
    extension = original.suffix.lower()
    annee = (instance.date_reception or timezone.localdate()).year
    return f"courriers/{annee}/{base}-{uuid4().hex[:12]}{extension}"


def generate_courrier_reference(year=None):
    """Construit la prochaine reference du type COUR-2026-001."""
    year = year or timezone.localdate().year
    prefix = f"{REFERENCE_PREFIX}-{year}-"
    derniere = (
        Courrier.objects.filter(reference__startswith=prefix)
        .order_by("-reference")
        .values_list("reference", flat=True)
        .first()
    )

    sequence = 1
    if derniere:
        try:
            sequence = int(derniere.rsplit("-", 1)[1]) + 1
        except (IndexError, ValueError):
            sequence = Courrier.objects.filter(reference__startswith=prefix).count() + 1

    return f"{prefix}{sequence:03d}"


class InstructionCourrier(models.Model):
    """Instruction cochable de la fiche : « Pour suite à donner », « A classer »…"""

    libelle = models.CharField(max_length=120, unique=True)
    ordre = models.PositiveIntegerField(default=0)
    actif = models.BooleanField(default=True)

    class Meta:
        ordering = ["ordre", "libelle"]
        verbose_name = "Instruction"
        verbose_name_plural = "Instructions"

    def __str__(self):
        return self.libelle


class Courrier(models.Model):
    class Sens(models.TextChoices):
        ENTRANT = "entrant", "Entrant"
        SORTANT = "sortant", "Sortant"

    class Priorite(models.TextChoices):
        NORMALE = "normale", "Normale"
        URGENTE = "urgente", "Urgente"

    class Status(models.TextChoices):
        RECU = "recu", "Reçu"
        EN_TRAITEMENT = "en_traitement", "En traitement"
        TRANSMIS_SECRETARIAT = "transmis_secretariat", "Transmis au secrétariat"
        TRANSMIS_DG = "transmis_dg", "Transmis au DG"
        VISE_DG = "vise_dg", "Visé par le DG"
        RETOURNE = "retourne", "Retourné pour suite à donner"
        CLASSE = "classe", "Classé"

    # Etapes ordonnees, pour l'indicateur de progression de la fiche.
    STATUS_FLOW = [
        Status.RECU,
        Status.EN_TRAITEMENT,
        Status.TRANSMIS_SECRETARIAT,
        Status.TRANSMIS_DG,
        Status.VISE_DG,
        Status.RETOURNE,
        Status.CLASSE,
    ]
    CLOSED_STATUSES = {Status.CLASSE}

    reference = models.CharField(
        max_length=40,
        unique=True,
        blank=True,
        help_text="Laisser vide pour une attribution automatique.",
    )
    sens = models.CharField(max_length=20, choices=Sens.choices, default=Sens.ENTRANT)
    numero_arrivee = models.CharField(
        max_length=60,
        blank=True,
        help_text="Numéro « COURRIER ARRIVÉE » porté sur la pièce à la réception.",
    )
    objet = models.CharField(max_length=255)
    expediteur = models.CharField(max_length=180)
    destinataire_service = models.ForeignKey(
        Service,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="courriers",
    )
    date_reception = models.DateField(default=timezone.localdate)
    date_courrier = models.DateField(
        null=True,
        blank=True,
        help_text="Date portée sur le courrier, si elle diffère de la réception.",
    )
    priorite = models.CharField(
        max_length=20,
        choices=Priorite.choices,
        default=Priorite.NORMALE,
    )
    fichier = models.FileField(upload_to=courrier_upload_path, blank=True)
    statut = models.CharField(max_length=25, choices=Status.choices, default=Status.RECU)
    observation = models.TextField(blank=True)
    instruction_dg = models.TextField(
        blank=True,
        help_text="Observations portées par le Directeur Général sur la fiche d'analyse.",
    )

    # --- Fiche d'analyse : la partie renseignée par le Directeur Général
    #
    # Les imputations visent directement les services et les agents existants,
    # et non une liste de libellés à maintenir en parallèle : créer un service
    # ou un compte suffit à le faire apparaître sur la fiche.
    services_imputes = models.ManyToManyField(
        Service,
        blank=True,
        related_name="courriers_imputes",
        verbose_name="Services imputés",
    )
    agents_imputes = models.ManyToManyField(
        User,
        blank=True,
        related_name="courriers_imputes",
        verbose_name="Agents imputés",
    )
    instructions = models.ManyToManyField(
        InstructionCourrier,
        blank=True,
        related_name="courriers",
        verbose_name="Instructions",
    )
    autres_instructions = models.TextField(
        blank=True,
        verbose_name="Autres instructions",
        help_text="Rubrique « AUTRES » de la fiche d'analyse.",
    )
    date_fiche = models.DateTimeField(null=True, blank=True)
    fiche_saisie_par = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="fiches_saisies",
    )
    fiche_pour_le_compte_du_dg = models.BooleanField(
        default=False,
        help_text=(
            "Vrai lorsque le secrétariat reporte une fiche annotée sur papier "
            "par le Directeur Général."
        ),
    )

    # Taches ouvertes pour donner suite au courrier. La relation est portee par
    # le courrier : l'application des courriers connait deja les taches,
    # l'inverse n'a pas lieu d'etre.
    taches = models.ManyToManyField(
        "tasks.Task",
        blank=True,
        related_name="courriers_origine",
        verbose_name="Tâches de suivi",
    )

    @property
    def taches_ouvertes(self):
        return self.taches.exclude(statut__in=["valide", "rejete", "archive"])

    @property
    def suite_donnee(self):
        """Toutes les tâches de suivi sont closes : la suite a été donnée."""
        return self.taches.exists() and not self.taches_ouvertes.exists()

    @property
    def libelles_imputations(self):
        """Imputations telles qu'elles s'impriment sur la fiche."""
        services = list(self.services_imputes.values_list("nom", flat=True))
        agents = [
            agent.get_full_name().strip() or agent.username
            for agent in self.agents_imputes.all()
        ]
        return services + agents

    @property
    def a_des_imputations(self):
        return self.services_imputes.exists() or self.agents_imputes.exists()

    # Tracabilite du circuit
    receptionne_par = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="courriers_receptionnes",
    )
    date_transmission_secretariat = models.DateTimeField(null=True, blank=True)
    date_transmission_dg = models.DateTimeField(null=True, blank=True)
    transmis_par = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="courriers_transmis",
    )
    date_visa = models.DateTimeField(null=True, blank=True)
    vise_par = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="courriers_vises",
    )
    date_retour = models.DateTimeField(null=True, blank=True)
    date_classement = models.DateTimeField(null=True, blank=True)
    cree_par = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="courriers_crees",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-date_reception", "-created_at"]
        verbose_name = "Courrier"
        verbose_name_plural = "Courriers"
        indexes = [
            models.Index(fields=["statut"], name="cour_statut_idx"),
            models.Index(fields=["-date_reception"], name="cour_reception_idx"),
            models.Index(fields=["expediteur"], name="cour_expediteur_idx"),
        ]

    def __str__(self):
        return f"{self.reference} - {self.objet}"

    def save(self, *args, **kwargs):
        if self.reference:
            return super().save(*args, **kwargs)

        year = self.date_reception.year if self.date_reception else None
        for _ in range(5):
            self.reference = generate_courrier_reference(year)
            try:
                with transaction.atomic():
                    return super().save(*args, **kwargs)
            except IntegrityError:
                self.reference = ""
        raise IntegrityError("Impossible d'attribuer une reference de courrier unique.")

    @property
    def nom_fichier(self):
        return Path(self.fichier.name).name if self.fichier else ""

    @property
    def is_closed(self):
        return self.statut in self.CLOSED_STATUSES

    @property
    def is_urgent(self):
        return self.priorite == self.Priorite.URGENTE and not self.is_closed

    @property
    def attente_visa(self):
        return self.statut == self.Status.TRANSMIS_DG

    @property
    def attente_visa_secretariat(self):
        return self.statut == self.Status.TRANSMIS_SECRETARIAT

    @property
    def jours_depuis_reception(self):
        return (timezone.localdate() - self.date_reception).days if self.date_reception else 0

    @property
    def etape_index(self):
        try:
            return self.STATUS_FLOW.index(self.statut) + 1
        except ValueError:
            return 0

    @property
    def status_badge_class(self):
        return {
            self.Status.RECU: "badge diploma-status-received",
            self.Status.EN_TRAITEMENT: "badge diploma-status-checking",
            self.Status.TRANSMIS_SECRETARIAT: "badge diploma-status-returned",
            self.Status.TRANSMIS_DG: "badge diploma-status-submitted",
            self.Status.VISE_DG: "badge diploma-status-signed",
            self.Status.RETOURNE: "badge diploma-status-compliant",
            self.Status.CLASSE: "badge diploma-status-archived",
        }.get(self.statut, "badge text-bg-light")


class CourrierHistory(models.Model):
    courrier = models.ForeignKey(
        Courrier,
        on_delete=models.CASCADE,
        related_name="historiques",
    )
    action = models.CharField(max_length=180)
    ancien_statut = models.CharField(max_length=25, blank=True)
    nouveau_statut = models.CharField(max_length=25, blank=True)
    commentaire = models.TextField(blank=True)
    utilisateur = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="courrier_histories",
    )
    date = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-date"]
        verbose_name = "Historique de courrier"
        verbose_name_plural = "Historiques de courrier"

    def __str__(self):
        return f"{self.courrier.reference} - {self.action}"
