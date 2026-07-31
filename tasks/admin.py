from django.contrib import admin

from .models import Task, TaskHistory


@admin.register(Task)
class TaskAdmin(admin.ModelAdmin):
    list_display = (
        "titre",
        "service_concerne",
        "assigne_a",
        "priorite",
        "display_status",
        "date_limite",
        "display_days_overdue",
    )
    list_filter = ("priorite", "statut", "service_concerne")
    search_fields = ("titre", "description")
    autocomplete_fields = ("service_concerne", "assigne_a", "cree_par")

    @admin.display(description="Statut")
    def display_status(self, obj):
        return obj.display_status_label

    @admin.display(description="Retard (jours)")
    def display_days_overdue(self, obj):
        return obj.days_overdue or "-"


@admin.register(TaskHistory)
class TaskHistoryAdmin(admin.ModelAdmin):
    list_display = ("tache", "action", "ancien_statut", "nouveau_statut", "utilisateur", "date")
    list_filter = ("ancien_statut", "nouveau_statut", "date")
    search_fields = ("tache__titre", "action", "utilisateur__username")

# Register your models here.
