from django.contrib import admin

from .models import Courrier, CourrierHistory, InstructionCourrier


@admin.register(InstructionCourrier)
class InstructionCourrierAdmin(admin.ModelAdmin):
    list_display = ("libelle", "ordre", "actif")
    list_filter = ("actif",)
    search_fields = ("libelle",)
    ordering = ("ordre", "libelle")


@admin.register(Courrier)
class CourrierAdmin(admin.ModelAdmin):
    list_display = (
        "reference",
        "objet",
        "expediteur",
        "sens",
        "nature",
        "priorite",
        "statut",
        "date_reception",
    )
    list_filter = ("statut", "sens", "nature", "priorite", "date_reception", "destinataire_service")
    search_fields = ("reference", "objet", "expediteur", "observation", "instruction_dg")
    autocomplete_fields = (
        "destinataire_service",
        "receptionne_par",
        "transmis_par",
        "vise_par",
        "cree_par",
    )
    readonly_fields = (
        "date_transmission_secretariat",
        "date_transmission_dg",
        "date_visa",
        "date_retour",
        "date_classement",
    )
    ordering = ("-date_reception",)


@admin.register(CourrierHistory)
class CourrierHistoryAdmin(admin.ModelAdmin):
    list_display = ("courrier", "action", "ancien_statut", "nouveau_statut", "utilisateur", "date")
    list_filter = ("nouveau_statut", "date")
    search_fields = ("courrier__reference", "action", "commentaire")
    ordering = ("-date",)
