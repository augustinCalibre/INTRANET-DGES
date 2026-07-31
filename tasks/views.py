from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from core.permissions import can_assign_to_anyone, is_admin_user
from core.utils import log_activity, safe_next_url

from .forms import TaskForm
from .models import Task, TaskHistory
from .selectors import can_modify_task, get_visible_tasks

ACTIVE_TASK_STATUSES = [
    Task.Status.NOUVEAU,
    Task.Status.EN_ATTENTE,
    Task.Status.EN_COURS,
    Task.Status.TRAITE,
]


def _register_history(task, user, action, previous_status="", current_status=""):
    TaskHistory.objects.create(
        tache=task,
        action=action,
        ancien_statut=previous_status,
        nouveau_statut=current_status,
        utilisateur=user,
    )


@login_required
def task_list(request):
    status_filter = request.GET.get("statut", "").strip()
    priority_filter = request.GET.get("priorite", "").strip()
    scope_filter = request.GET.get("scope", "").strip()
    search_term = request.GET.get("q", "").strip()
    tasks = get_visible_tasks(request.user)
    active_filter_label = ""

    if scope_filter == "active":
        tasks = tasks.filter(statut__in=ACTIVE_TASK_STATUSES)
        active_filter_label = "Taches ouvertes et en cours"

    if status_filter:
        tasks = tasks.filter(statut=status_filter)
        active_filter_label = Task.Status(status_filter).label
    if priority_filter:
        tasks = tasks.filter(priorite=priority_filter)
    if search_term:
        tasks = tasks.filter(
            Q(titre__icontains=search_term)
            | Q(description__icontains=search_term)
            | Q(service_concerne__nom__icontains=search_term)
        )

    return render(
        request,
        "tasks/list.html",
        {
            "tasks": tasks,
            "status_filter": status_filter,
            "priority_filter": priority_filter,
            "scope_filter": scope_filter,
            "search_term": search_term,
            "status_choices": Task.Status.choices,
            "priority_choices": Task.Priority.choices,
            "active_filter_label": active_filter_label,
            "today": timezone.localdate(),
            "can_delete": is_admin_user(request.user),
        },
    )


@login_required
def task_create(request):
    if request.method == "POST":
        form = TaskForm(request.POST, user=request.user)
        if form.is_valid():
            task = form.save(commit=False)
            task.cree_par = request.user
            task.save()
            form.save_m2m()
            _register_history(task, request.user, "Création de la tâche", "", task.statut)
            log_activity(request.user, "Création d'une tâche", "Tâches", task.titre)
            messages.success(request, "La tâche a été créée.")
            return redirect("tasks:list")
    else:
        initial = {}
        profile = getattr(request.user, "profil", None)
        if profile and profile.service_id:
            initial["service_concerne"] = profile.service
        form = TaskForm(initial=initial, user=request.user)

    return render(
        request,
        "tasks/form.html",
        {
            "form": form,
            "title": "Nouvelle tâche",
            "histories": [],
            "is_creation": True,
        },
    )


@login_required
def task_edit(request, pk):
    task = get_object_or_404(get_visible_tasks(request.user), pk=pk)
    if not can_modify_task(task, request.user):
        raise PermissionDenied

    previous_status = task.statut

    if request.method == "POST":
        form = TaskForm(request.POST, instance=task, user=request.user)
        if form.is_valid():
            task = form.save()
            action = "Mise à jour de la tâche"
            if previous_status != task.statut:
                action = "Changement de statut"
            _register_history(task, request.user, action, previous_status, task.statut)

            # Une tâche née d'un courrier fait remonter son avancement dans
            # l'historique de ce courrier : l'agent traite sa tâche, le
            # secrétariat voit la suite donnée.
            if previous_status != task.statut:
                from courriers.services import record_task_progress

                record_task_progress(task, request.user, previous_status)

            log_activity(request.user, "Mise à jour d'une tâche", "Tâches", task.titre)
            messages.success(request, "La tâche a été mise à jour.")
            return redirect("tasks:list")
    else:
        form = TaskForm(instance=task, user=request.user)

    return render(
        request,
        "tasks/form.html",
        {
            "form": form,
            "title": f"Modifier {task.titre}",
            "task": task,
            "histories": task.historiques.select_related("utilisateur")[:10],
            "is_creation": False,
            "can_assign": can_assign_to_anyone(request.user),
        },
    )


@login_required
def kanban_view(request):
    tasks = get_visible_tasks(request.user)
    columns = [
        {
            "key": status,
            "label": label,
            "tasks": tasks.filter(statut=status),
        }
        for status, label in Task.Status.choices
    ]
    return render(
        request,
        "tasks/kanban.html",
        {
            "columns": columns,
        },
    )


@login_required
@require_POST
def task_delete(request, pk):
    if not is_admin_user(request.user):
        raise PermissionDenied

    task = get_object_or_404(Task, pk=pk)
    task_title = task.titre
    task.delete()
    log_activity(request.user, "Suppression d'une tache", "Taches", task_title)
    messages.success(request, "La tache a ete supprimee.")
    return redirect(safe_next_url(request, request.POST.get("next"), "tasks:list"))

# Create your views here.
