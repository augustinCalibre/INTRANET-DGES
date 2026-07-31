import mimetypes

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.http import FileResponse, Http404
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from core.permissions import can_manage_courriers, can_manage_documents, is_admin_user
from core.utils import log_activity, safe_next_url

from .forms import DocumentForm
from .models import Document
from .selectors import get_visible_documents


def _document_type_label(type_value):
    for value, label in Document.Type.choices:
        if value == type_value:
            return label
    return ""


@login_required
def document_list(request):
    type_filter = request.GET.get("type", "").strip()
    if not type_filter and getattr(request, "resolver_match", None) and request.resolver_match.url_name == "courriers":
        type_filter = Document.Type.COURRIER
    status_filter = request.GET.get("statut", "").strip()
    period_filter = request.GET.get("periode", "").strip()
    search_term = request.GET.get("q", "").strip()
    documents = get_visible_documents(request.user)
    active_filter_label = ""
    is_courrier_view = type_filter == Document.Type.COURRIER

    if period_filter == "today":
        documents = documents.filter(date_ajout__date=timezone.localdate())
        active_filter_label = "Documents du jour"

    if type_filter:
        documents = documents.filter(type_document=type_filter)
        if not active_filter_label:
            active_filter_label = _document_type_label(type_filter)
    if status_filter:
        documents = documents.filter(statut=status_filter)
    if search_term:
        documents = documents.filter(
            Q(titre__icontains=search_term)
            | Q(service_concerne__nom__icontains=search_term)
            | Q(auteur__username__icontains=search_term)
        )

    return render(
        request,
        "documents/list.html",
        {
            "documents": documents,
            "type_filter": type_filter,
            "status_filter": status_filter,
            "period_filter": period_filter,
            "search_term": search_term,
            "type_choices": Document.Type.choices,
            "status_choices": Document.Status.choices,
            "can_manage": can_manage_documents(request.user),
            "can_delete": is_admin_user(request.user),
            "active_filter_label": active_filter_label,
            "is_courrier_view": is_courrier_view,
        },
    )


@login_required
def document_create(request):
    if not can_manage_documents(request.user):
        raise PermissionDenied

    if request.method == "POST":
        form = DocumentForm(request.POST, request.FILES, user=request.user)
        if form.is_valid():
            document = form.save(commit=False)
            document.auteur = request.user
            document.save()
            log_activity(request.user, "Ajout d'un document", "Documents", document.titre)
            messages.success(request, "Le document a ete ajoute.")
            if document.type_document == Document.Type.COURRIER:
                return redirect(f"{reverse('documents:list')}?type={Document.Type.COURRIER}")
            return redirect("documents:list")
    else:
        initial = {}
        requested_type = request.GET.get("type", "").strip()
        profile = getattr(request.user, "profil", None)
        if profile and profile.service_id and not can_manage_courriers(request.user):
            initial["service_concerne"] = profile.service
        if requested_type in {choice[0] for choice in Document.Type.choices}:
            initial["type_document"] = requested_type
        form = DocumentForm(initial=initial, user=request.user)

    return render(
        request,
        "documents/form.html",
        {
            "form": form,
            "title": "Ajouter un document",
            "is_creation": True,
            "return_url": (
                f"{reverse('documents:list')}?type={Document.Type.COURRIER}"
                if request.GET.get("type", "").strip() == Document.Type.COURRIER
                else reverse("documents:list")
            ),
            "return_label": (
                "Retour aux courriers"
                if request.GET.get("type", "").strip() == Document.Type.COURRIER
                else "Retour a la liste"
            ),
        },
    )


@login_required
def document_edit(request, pk):
    if not can_manage_documents(request.user):
        raise PermissionDenied

    document = get_object_or_404(get_visible_documents(request.user), pk=pk)
    previous_file_name = document.fichier.name if document.fichier else ""

    if request.method == "POST":
        form = DocumentForm(request.POST, request.FILES, instance=document, user=request.user)
        if form.is_valid():
            document = form.save(commit=False)
            document.auteur = document.auteur or request.user
            document.save()
            if (
                form.cleaned_data.get("fichier")
                and previous_file_name
                and previous_file_name != document.fichier.name
            ):
                document.fichier.storage.delete(previous_file_name)
            log_activity(request.user, "Mise a jour d'un document", "Documents", document.titre)
            messages.success(request, "Le document a ete mis a jour.")
            if document.type_document == Document.Type.COURRIER:
                return redirect(f"{reverse('documents:list')}?type={Document.Type.COURRIER}")
            return redirect("documents:list")
    else:
        form = DocumentForm(instance=document, user=request.user)

    return render(
        request,
        "documents/form.html",
        {
            "form": form,
            "title": f"Modifier {document.titre}",
            "document": document,
            "is_creation": False,
            "return_url": (
                f"{reverse('documents:list')}?type={Document.Type.COURRIER}"
                if document.type_document == Document.Type.COURRIER
                else reverse("documents:list")
            ),
            "return_label": (
                "Retour aux courriers"
                if document.type_document == Document.Type.COURRIER
                else "Retour a la liste"
            ),
        },
    )


@login_required
def document_download(request, pk):
    document = get_object_or_404(get_visible_documents(request.user), pk=pk)
    if not document.fichier:
        raise Http404("Fichier introuvable.")

    guessed_content_type = mimetypes.guess_type(document.fichier.name)[0] or "application/octet-stream"
    response = FileResponse(
        document.fichier.open("rb"),
        as_attachment=True,
        filename=document.nom_fichier,
        content_type=guessed_content_type,
    )
    response["X-Content-Type-Options"] = "nosniff"
    return response


@login_required
@require_POST
def document_delete(request, pk):
    if not is_admin_user(request.user):
        raise PermissionDenied

    document = get_object_or_404(Document, pk=pk)
    document_title = document.titre
    if document.fichier:
        document.fichier.delete(save=False)
    document.delete()
    log_activity(request.user, "Suppression d'un document", "Documents", document_title)
    messages.success(request, "Le document a ete supprime.")
    return redirect(safe_next_url(request, request.POST.get("next"), "documents:list"))
