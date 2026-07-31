from django.contrib import admin

from .models import Document


@admin.register(Document)
class DocumentAdmin(admin.ModelAdmin):
    list_display = ("titre", "type_document", "service_concerne", "auteur", "statut", "date_ajout")
    list_filter = ("type_document", "statut", "service_concerne")
    search_fields = ("titre", "service_concerne__nom", "auteur__username")
    autocomplete_fields = ("service_concerne", "auteur")

# Register your models here.
