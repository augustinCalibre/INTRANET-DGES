from django.contrib import admin
from django.urls import include, path

admin.site.site_header = "Administration Intranet DGES"
admin.site.site_title = "Intranet DGES"
admin.site.index_title = "Console d'administration"

urlpatterns = [
    path("admin/", admin.site.urls),
    path("accounts/", include(("accounts.urls", "accounts"), namespace="accounts")),
    path("dashboard/", include(("dashboard.urls", "dashboard"), namespace="dashboard")),
    path("visitors/", include(("visitors.urls", "visitors"), namespace="visitors")),
    path("tasks/", include(("tasks.urls", "tasks"), namespace="tasks")),
    path("documents/", include(("documents.urls", "documents"), namespace="documents")),
    path("meetings/", include(("meetings.urls", "meetings"), namespace="meetings")),
    path("diplomes/", include(("diplomas.urls", "diplomas"), namespace="diplomas")),
    path("bordereaux/", include(("bordereaux.urls", "bordereaux"), namespace="bordereaux")),
    path("courriers/", include(("courriers.urls", "courriers"), namespace="courriers")),
    path(
        "exploitation/",
        include(("exploitation.urls", "exploitation"), namespace="exploitation"),
    ),
    path("", include(("core.urls", "core"), namespace="core")),
]
