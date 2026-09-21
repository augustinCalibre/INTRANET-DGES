from django.urls import path

from .views import (
    boite,
    bordereau_create,
    bordereau_delete,
    bordereau_detail,
    bordereau_edit,
    bordereau_fichier,
    bordereau_signer,
    export,
    organisme_create,
    organisme_delete,
    organisme_edit,
    organisme_list,
    tableau,
)

app_name = "bordereaux"

urlpatterns = [
    path("", tableau, name="tableau"),
    path("organismes/", organisme_list, name="organisme_list"),
    path("organismes/nouveau/", organisme_create, name="organisme_create"),
    path("organismes/<int:pk>/modifier/", organisme_edit, name="organisme_edit"),
    path("organismes/<int:pk>/supprimer/", organisme_delete, name="organisme_delete"),
    path("nouveau/", bordereau_create, name="create"),
    path("export/", export, name="export"),
    path("fiche/<int:pk>/", bordereau_detail, name="detail"),
    path("fiche/<int:pk>/modifier/", bordereau_edit, name="edit"),
    path("fiche/<int:pk>/piece/", bordereau_fichier, name="fichier"),
    path("fiche/<int:pk>/signer/<str:etape>/", bordereau_signer, name="signer"),
    path("fiche/<int:pk>/supprimer/", bordereau_delete, name="delete"),
    path("<int:annee>/", tableau, name="tableau_annee"),
    path("<int:annee>/export/", export, name="export_annee"),
    path(
        "<int:annee>/T<int:trimestre>/<int:organisme_pk>/",
        boite,
        name="boite",
    ),
]
