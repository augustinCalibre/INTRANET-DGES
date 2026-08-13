from django.urls import path

from .views import (
    diploma_create,
    diploma_delete,
    diploma_detail,
    diploma_edit,
    diploma_mark_compliant,
    diploma_search,
    diploma_withdraw,
    lot_create,
    lot_delete,
    lot_detail,
    lot_edit,
    lot_export,
    lot_list,
    lot_liste_download,
    lot_status,
    registry_export,
)

app_name = "diplomas"

urlpatterns = [
    path("", lot_list, name="lot_list"),
    path("recherche/", diploma_search, name="search"),
    path("export/", registry_export, name="registry_export"),
    path("nouveau/", lot_create, name="lot_create"),
    path("<int:pk>/", lot_detail, name="lot_detail"),
    path("<int:pk>/modifier/", lot_edit, name="lot_edit"),
    path("<int:pk>/export/", lot_export, name="lot_export"),
    path("<int:pk>/statut/<str:statut>/", lot_status, name="lot_status"),
    path("<int:pk>/supprimer/", lot_delete, name="lot_delete"),
    path("<int:lot_pk>/diplomes/ajouter/", diploma_create, name="diploma_create"),
    path("<int:pk>/liste/", lot_liste_download, name="lot_liste_download"),
    path("diplomes/<int:pk>/", diploma_detail, name="diploma_detail"),
    path("diplomes/<int:pk>/modifier/", diploma_edit, name="diploma_edit"),
    path("diplomes/<int:pk>/conforme/", diploma_mark_compliant, name="diploma_mark_compliant"),
    path("diplomes/<int:pk>/retrait/", diploma_withdraw, name="diploma_withdraw"),
    path("diplomes/<int:pk>/supprimer/", diploma_delete, name="diploma_delete"),
]
