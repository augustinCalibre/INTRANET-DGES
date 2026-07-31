from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from core.permissions import can_manage_visitors, is_admin_user
from core.utils import log_activity, safe_next_url

from .forms import VisitorForm
from .models import Visitor
from .selectors import get_visible_visitors


@login_required
def visitor_list(request):
    status_filter = request.GET.get("statut", "").strip()
    period_filter = request.GET.get("periode", "").strip()
    search_term = request.GET.get("q", "").strip()
    visitors = get_visible_visitors(request.user)
    active_filter_label = ""

    if period_filter == "today":
        visitors = visitors.filter(heure_entree__date=timezone.localdate())
        active_filter_label = "Visiteurs du jour"

    if status_filter:
        visitors = visitors.filter(statut=status_filter)
        active_filter_label = Visitor.Status(status_filter).label
    if search_term:
        visitors = visitors.filter(
            Q(nom_complet__icontains=search_term)
            | Q(contact__icontains=search_term)
            | Q(provenance__icontains=search_term)
            | Q(motif__icontains=search_term)
        )

    return render(
        request,
        "visitors/list.html",
        {
            "visitors": visitors,
            "status_filter": status_filter,
            "period_filter": period_filter,
            "search_term": search_term,
            "status_choices": Visitor.Status.choices,
            "can_manage": can_manage_visitors(request.user),
            "can_delete": is_admin_user(request.user),
            "active_filter_label": active_filter_label,
        },
    )


@login_required
def visitor_create(request):
    if not can_manage_visitors(request.user):
        raise PermissionDenied

    if request.method == "POST":
        form = VisitorForm(request.POST)
        if form.is_valid():
            visitor = form.save(commit=False)
            visitor.cree_par = request.user
            visitor.save()
            log_activity(request.user, "Enregistrement d'un visiteur", "Visiteurs", visitor.nom_complet)
            messages.success(request, "Le visiteur a ete enregistre.")
            return redirect("visitors:list")
    else:
        form = VisitorForm()

    return render(
        request,
        "visitors/form.html",
        {
            "form": form,
            "title": "Nouveau visiteur",
            "is_creation": True,
        },
    )


@login_required
def visitor_edit(request, pk):
    if not can_manage_visitors(request.user):
        raise PermissionDenied

    visitor = get_object_or_404(get_visible_visitors(request.user), pk=pk)

    if request.method == "POST":
        form = VisitorForm(request.POST, instance=visitor)
        if form.is_valid():
            visitor = form.save()
            log_activity(request.user, "Mise a jour d'un visiteur", "Visiteurs", visitor.nom_complet)
            messages.success(request, "Les informations du visiteur ont ete mises a jour.")
            return redirect("visitors:list")
    else:
        form = VisitorForm(instance=visitor)

    return render(
        request,
        "visitors/form.html",
        {
            "form": form,
            "title": f"Modifier {visitor.nom_complet}",
            "visitor": visitor,
            "is_creation": False,
        },
    )


@login_required
@require_POST
def visitor_checkout(request, pk):
    if not can_manage_visitors(request.user):
        raise PermissionDenied

    visitor = get_object_or_404(get_visible_visitors(request.user), pk=pk)
    if visitor.statut != Visitor.Status.SORTI:
        visitor.marquer_sortie()
        log_activity(request.user, "Sortie d'un visiteur", "Visiteurs", visitor.nom_complet)
        messages.success(request, "La sortie du visiteur a ete enregistree.")
    else:
        messages.info(request, "Ce visiteur est deja marque comme sorti.")
    return redirect(safe_next_url(request, request.POST.get("next"), "visitors:list"))


@login_required
@require_POST
def visitor_delete(request, pk):
    if not is_admin_user(request.user):
        raise PermissionDenied

    visitor = get_object_or_404(Visitor, pk=pk)
    visitor_name = visitor.nom_complet
    visitor.delete()
    log_activity(request.user, "Suppression d'un visiteur", "Visiteurs", visitor_name)
    messages.success(request, "Le visiteur a ete supprime.")
    return redirect(safe_next_url(request, request.POST.get("next"), "visitors:list"))
