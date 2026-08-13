from django.contrib import admin

from .models import Diplome, DiplomeHistory, LotDiplomes, LotHistory


class DiplomeInline(admin.TabularInline):
    model = Diplome
    extra = 0
    fields = ("nom_beneficiaire", "numero_diplome", "filiere", "annee_academique", "statut", "anomalie")
    show_change_link = True


@admin.register(LotDiplomes)
class LotDiplomesAdmin(admin.ModelAdmin):
    list_display = (
        "reference",
        "etablissement",
        "date_arrivee",
        "nombre_annonce",
        "display_nombre_conformes",
        "display_nombre_anomalies",
        "statut",
        "agent_receptionnaire",
    )
    list_filter = ("statut", "date_arrivee", "service_concerne")
    search_fields = ("reference", "etablissement", "observation")
    autocomplete_fields = ("agent_receptionnaire", "service_concerne", "transmis_par", "signe_par", "cree_par")
    readonly_fields = ("date_transmission_dg", "date_signature", "date_retour", "date_remise")
    inlines = (DiplomeInline,)
    ordering = ("-date_arrivee",)

    @admin.display(description="Enregistrés")
    def display_nombre_conformes(self, obj):
        return obj.nombre_conformes

    def display_nombre_anomalies(self, obj):
        return obj.nombre_anomalies


@admin.register(Diplome)
class DiplomeAdmin(admin.ModelAdmin):
    list_display = (
        "nom_beneficiaire",
        "numero_diplome",
        "lot",
        "filiere",
        "annee_academique",
        "statut",
        "anomalie",
    )
    list_filter = ("statut", "anomalie", "annee_academique")
    search_fields = ("nom_beneficiaire", "numero_diplome", "filiere", "etablissement", "lot__reference")
    autocomplete_fields = ("lot",)


@admin.register(LotHistory)
class LotHistoryAdmin(admin.ModelAdmin):
    list_display = ("lot", "action", "ancien_statut", "nouveau_statut", "utilisateur", "date")
    list_filter = ("nouveau_statut", "date")
    search_fields = ("lot__reference", "action", "commentaire")
    ordering = ("-date",)


@admin.register(DiplomeHistory)
class DiplomeHistoryAdmin(admin.ModelAdmin):
    list_display = ("diplome", "action", "ancien_statut", "nouveau_statut", "utilisateur", "date")
    list_filter = ("nouveau_statut", "date")
    search_fields = ("diplome__numero_diplome", "diplome__nom_beneficiaire", "action")
    ordering = ("-date",)
