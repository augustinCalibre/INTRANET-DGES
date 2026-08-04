from django.urls import path

from .views import (
    courrier_create,
    courrier_decharge,
    courrier_delete,
    courrier_detail,
    courrier_download,
    courrier_edit,
    courrier_export,
    courrier_fiche,
    courrier_fiche_print,
    courrier_list,
    courrier_status,
)

app_name = "courriers"

urlpatterns = [
    path("", courrier_list, name="list"),
    path("export/", courrier_export, name="export"),
    path("nouveau/", courrier_create, name="create"),
    path("<int:pk>/", courrier_detail, name="detail"),
    path("<int:pk>/modifier/", courrier_edit, name="edit"),
    path("<int:pk>/piece/", courrier_download, name="download"),
    path("<int:pk>/fiche/", courrier_fiche, name="fiche"),
    path("<int:pk>/fiche/imprimer/", courrier_fiche_print, name="fiche_print"),
    path("<int:pk>/decharge/", courrier_decharge, name="decharge"),
    path("<int:pk>/statut/<str:statut>/", courrier_status, name="status"),
    path("<int:pk>/supprimer/", courrier_delete, name="delete"),
]
