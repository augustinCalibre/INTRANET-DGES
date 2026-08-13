from pathlib import Path
from uuid import uuid4

from django.contrib.auth.models import User
from django.db import IntegrityError, models, transaction
from django.utils import timezone
from django.utils.text import slugify

from accounts.models import Service

REFERENCE_PREFIX = "LOT-DIP"


def liste_lot_upload_path(instance, filename):
    original = Path(filename)
    base = slugify(original.stem) or "liste"
    annee = (instance.date_arrivee or timezone.localdate()).year
    return f"diplomes/listes/{annee}/{base}-{uuid4().hex[:12]}{original.suffix.lower()}"


def generate_lot_reference(year=None):
    """Construit la prochaine reference disponible du type LOT-DIP-2026-001."""
    year = year or timezone.localdate().year
    prefix = f"{REFERENCE_PREFIX}-{year}-"
    last_reference = (
        LotDiplomes.objects.filter(reference__startswith=prefix)
        .order_by("-reference")
        .values_list("reference", flat=True)
        .first()
    )

    sequence = 1
    if last_reference:
        try:
            sequence = int(last_reference.rsplit("-", 1)[1]) + 1
        except (IndexError, ValueError):
            sequence = LotDiplomes.objects.filter(reference__startswith=prefix).count() + 1

    return f"{prefix}{sequence:03d}"


class LotDiplomes(models.Model):
    class Status(models.TextChoices):
        RECU = "recu", "Reçu"
        EN_VERIFICATION = "en_verification", "En vérification"
        CONFORME = "conforme", "Conforme"
        TRANSMIS_DG = "transmis_dg", "Transmis au DG"
        SIGNE = "signe", "Signé"
        RETOURNE = "retourne", "Retourné au service"
        REMIS = "remis", "Remis"
        ARCHIVE = "archive", "Archivé"

    # Etapes ordonnees, utilisees pour l'indicateur de progression de la fiche lot.
    STATUS_FLOW = [
        Status.RECU,
        Status.EN_VERIFICATION,
        Status.CONFORME,
        Status.TRANSMIS_DG,
        Status.SIGNE,
        Status.RETOURNE,
        Status.REMIS,
        Status.ARCHIVE,
    ]
    CLOSED_STATUSES = {Status.REMIS, Status.ARCHIVE}

    reference = models.CharField(
        max_length=40,
        unique=True,
        blank=True,
        help_text="Laisser vide pour une attribution automatique.",
    )
    etablissement = models.CharField(max_length=180)
    date_arrivee = models.DateField(default=timezone.localdate)
    nombre_annonce = models.PositiveIntegerField(default=0)
    # La liste remise par l'etablissement, telle qu'elle arrive : un PDF ou un
    # document Word. Elle n'est pas depouillee ligne a ligne — seuls les
    # diplomes non conformes sont saisis, le reste etant valide d'office. Le
    # fichier reste la piece de reference en cas de contestation.
    fichier_liste = models.FileField(
        upload_to=liste_lot_upload_path,
        blank=True,
        verbose_name="Liste des diplômes",
    )
    agent_receptionnaire = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="lots_receptionnes",
    )
    service_concerne = models.ForeignKey(
        Service,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="lots_diplomes",
    )
    statut = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.RECU,
    )
    observation = models.TextField(blank=True)
    date_transmission_dg = models.DateTimeField(null=True, blank=True)
    transmis_par = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="lots_transmis",
    )
    date_signature = models.DateTimeField(null=True, blank=True)
    signe_par = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="lots_signes",
    )
    date_retour = models.DateTimeField(null=True, blank=True)
    date_remise = models.DateTimeField(null=True, blank=True)
    cree_par = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="lots_crees",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-date_arrivee", "-created_at"]
        verbose_name = "Lot de diplômes"
        verbose_name_plural = "Lots de diplômes"
        indexes = [
            models.Index(fields=["statut"], name="dip_lot_statut_idx"),
            models.Index(fields=["-date_arrivee"], name="dip_lot_arrivee_idx"),
        ]

    def __str__(self):
        return f"{self.reference} - {self.etablissement}"

    def save(self, *args, **kwargs):
        if self.reference:
            return super().save(*args, **kwargs)

        year = self.date_arrivee.year if self.date_arrivee else None
        for _ in range(5):
            self.reference = generate_lot_reference(year)
            try:
                with transaction.atomic():
                    return super().save(*args, **kwargs)
            except IntegrityError:
                self.reference = ""
        raise IntegrityError("Impossible d'attribuer une reference de lot unique.")

    # -- Compteurs -----------------------------------------------------
    # Les proprietes privilegient les annotations posees par les selectors
    # afin d'eviter une requete par ligne dans les listes.

    @property
    def nombre_enregistre(self):
        annotated = getattr(self, "nb_diplomes", None)
        if annotated is not None:
            return annotated
        return self.diplomes.count()

    @property
    def nombre_anomalies(self):
        annotated = getattr(self, "nb_anomalies", None)
        if annotated is not None:
            return annotated
        return self.diplomes.filter(statut=Diplome.Status.NON_CONFORME).count()

    @property
    def has_anomalies(self):
        return self.nombre_anomalies > 0

    @property
    def nombre_conformes(self):
        """Les diplômes du lot qui n'ont soulevé aucune anomalie.

        Ils ne sont pas saisis un à un : la vérification consiste à relever
        les diplômes non conformes, et la différence avec le nombre annoncé
        est conforme d'office. Dépouiller ligne à ligne une liste de deux
        cents diplômes pour n'en signaler que trois n'a jamais eu de sens.
        """
        return max(0, self.nombre_annonce - self.nombre_anomalies)

    @property
    def ecart(self):
        """Anomalies relevées au-delà du nombre annoncé.

        Toujours nul en temps normal. Une valeur positive dit qu'on a signalé
        plus de diplômes non conformes que l'établissement n'en a annoncé :
        c'est le nombre annoncé qui est faux, ou une saisie en double.
        """
        return max(0, self.nombre_anomalies - self.nombre_annonce)

    @property
    def has_ecart(self):
        return self.nombre_annonce > 0 and self.ecart > 0

    @property
    def ecart_label(self):
        if not self.has_ecart:
            return ""
        return (
            f"{self.ecart} anomalie{'s' if self.ecart > 1 else ''} de plus "
            "que le nombre annoncé"
        )

    @property
    def taux_conformite(self):
        """Part des diplômes conformes, en pourcentage."""
        if not self.nombre_annonce:
            return 0
        return max(0, min(100, round(self.nombre_conformes * 100 / self.nombre_annonce)))

    @property
    def is_closed(self):
        return self.statut in self.CLOSED_STATUSES

    @property
    def attente_signature(self):
        return self.statut == self.Status.TRANSMIS_DG

    @property
    def allows_diploma_edition(self):
        """Le contenu du lot n'est modifiable qu'avant la transmission au DG."""
        return self.statut in {
            self.Status.RECU,
            self.Status.EN_VERIFICATION,
            self.Status.CONFORME,
        }

    @property
    def allows_withdrawal(self):
        """Le retrait d'un diplome ne se trace qu'apres signature."""
        return self.statut in {
            self.Status.SIGNE,
            self.Status.RETOURNE,
            self.Status.REMIS,
        }

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
            self.Status.EN_VERIFICATION: "badge diploma-status-checking",
            self.Status.CONFORME: "badge diploma-status-compliant",
            self.Status.TRANSMIS_DG: "badge diploma-status-submitted",
            self.Status.SIGNE: "badge diploma-status-signed",
            self.Status.RETOURNE: "badge diploma-status-returned",
            self.Status.REMIS: "badge diploma-status-delivered",
            self.Status.ARCHIVE: "badge diploma-status-archived",
        }.get(self.statut, "badge text-bg-light")


class Diplome(models.Model):
    class Status(models.TextChoices):
        A_VERIFIER = "a_verifier", "À vérifier"
        CONFORME = "conforme", "Conforme"
        NON_CONFORME = "non_conforme", "Non conforme"
        TRANSMIS_DG = "transmis_dg", "Transmis au DG"
        SIGNE = "signe", "Signé"
        RETIRE = "retire", "Retiré"
        ARCHIVE = "archive", "Archivé"

    class Anomalie(models.TextChoices):
        MANQUANT = "manquant", "Diplôme manquant"
        ERREUR_NOM = "erreur_nom", "Erreur sur le nom"
        REFERENCE_INCORRECTE = "reference_incorrecte", "Référence incorrecte"
        PIECE_NON_CONFORME = "piece_non_conforme", "Pièce non conforme"
        AUTRE = "autre", "Autre anomalie"

    lot = models.ForeignKey(
        LotDiplomes,
        on_delete=models.CASCADE,
        related_name="diplomes",
    )
    nom_beneficiaire = models.CharField(max_length=180)
    numero_diplome = models.CharField(max_length=80)
    filiere = models.CharField(max_length=150, blank=True)
    etablissement = models.CharField(max_length=180, blank=True)
    annee_academique = models.CharField(max_length=20, blank=True)
    statut = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.A_VERIFIER,
    )
    anomalie = models.CharField(
        max_length=30,
        choices=Anomalie.choices,
        blank=True,
    )
    observations = models.TextField(blank=True)
    date_retrait = models.DateTimeField(null=True, blank=True)
    retire_par = models.CharField(
        max_length=180,
        blank=True,
        help_text="Personne ayant retiré le diplôme.",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["nom_beneficiaire", "numero_diplome"]
        verbose_name = "Diplôme"
        verbose_name_plural = "Diplômes"
        constraints = [
            models.UniqueConstraint(
                fields=["lot", "numero_diplome"],
                name="unique_numero_diplome_par_lot",
            )
        ]
        indexes = [
            models.Index(fields=["numero_diplome"], name="dip_numero_idx"),
            models.Index(fields=["nom_beneficiaire"], name="dip_nom_idx"),
            models.Index(fields=["statut"], name="dip_statut_idx"),
        ]

    def __str__(self):
        return f"{self.nom_beneficiaire} ({self.numero_diplome})"

    @property
    def etablissement_effectif(self):
        return self.etablissement or self.lot.etablissement

    @property
    def is_anomalie(self):
        return self.statut == self.Status.NON_CONFORME or bool(self.anomalie)

    @property
    def status_badge_class(self):
        return {
            self.Status.A_VERIFIER: "badge diploma-status-received",
            self.Status.CONFORME: "badge diploma-status-compliant",
            self.Status.NON_CONFORME: "badge diploma-status-anomaly",
            self.Status.TRANSMIS_DG: "badge diploma-status-submitted",
            self.Status.SIGNE: "badge diploma-status-signed",
            self.Status.RETIRE: "badge diploma-status-delivered",
            self.Status.ARCHIVE: "badge diploma-status-archived",
        }.get(self.statut, "badge text-bg-light")


class LotHistory(models.Model):
    lot = models.ForeignKey(
        LotDiplomes,
        on_delete=models.CASCADE,
        related_name="historiques",
    )
    action = models.CharField(max_length=180)
    ancien_statut = models.CharField(max_length=20, blank=True)
    nouveau_statut = models.CharField(max_length=20, blank=True)
    commentaire = models.TextField(blank=True)
    utilisateur = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="lot_histories",
    )
    date = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-date"]
        verbose_name = "Historique de lot"
        verbose_name_plural = "Historiques de lot"

    def __str__(self):
        return f"{self.lot.reference} - {self.action}"


class DiplomeHistory(models.Model):
    diplome = models.ForeignKey(
        Diplome,
        on_delete=models.CASCADE,
        related_name="historiques",
    )
    action = models.CharField(max_length=180)
    ancien_statut = models.CharField(max_length=20, blank=True)
    nouveau_statut = models.CharField(max_length=20, blank=True)
    commentaire = models.TextField(blank=True)
    utilisateur = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="diplome_histories",
    )
    date = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-date"]
        verbose_name = "Historique de diplôme"
        verbose_name_plural = "Historiques de diplôme"

    def __str__(self):
        return f"{self.diplome.numero_diplome} - {self.action}"
