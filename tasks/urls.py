from django.urls import path

from .views import kanban_view, task_create, task_delete, task_edit, task_list

app_name = "tasks"

urlpatterns = [
    path("", task_list, name="list"),
    path("add/", task_create, name="create"),
    path("<int:pk>/edit/", task_edit, name="edit"),
    path("<int:pk>/delete/", task_delete, name="delete"),
    path("kanban/", kanban_view, name="kanban"),
]
