from django.urls import path

from .views import (
    DGESLoginView,
    DGESLogoutView,
    access_panel,
    connexion_history,
    password_change,
    service_create,
    service_delete,
    service_edit,
    service_list,
    user_create,
    user_delete,
    user_edit,
    user_list,
    user_password_reset,
    user_toggle_active,
)

app_name = "accounts"

urlpatterns = [
    path("login/", DGESLoginView.as_view(), name="login"),
    path("logout/", DGESLogoutView.as_view(), name="logout"),
    path("mot-de-passe/", password_change, name="password_change"),
    path("acces/", access_panel, name="access_panel"),
    path("acces/connexions/", connexion_history, name="connexion_history"),
    path("services/", service_list, name="service_list"),
    path("services/nouveau/", service_create, name="service_create"),
    path("services/<int:pk>/modifier/", service_edit, name="service_edit"),
    path("services/<int:pk>/supprimer/", service_delete, name="service_delete"),
    path("users/", user_list, name="user_list"),
    path("users/add/", user_create, name="user_create"),
    path("users/<int:pk>/edit/", user_edit, name="user_edit"),
    path("users/<int:pk>/delete/", user_delete, name="user_delete"),
    path("users/<int:pk>/mot-de-passe/", user_password_reset, name="user_password_reset"),
    path("users/<int:pk>/activation/", user_toggle_active, name="user_toggle_active"),
]
