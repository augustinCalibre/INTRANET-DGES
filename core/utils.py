from django.core.paginator import Paginator
from django.shortcuts import resolve_url
from django.utils.http import url_has_allowed_host_and_scheme

from .models import ActivityLog

DEFAULT_PAGE_SIZE = 25


def log_activity(user, action, module, obj):
    ActivityLog.objects.create(
        utilisateur=user if getattr(user, "is_authenticated", False) else None,
        action=action,
        module=module,
        objet=str(obj),
    )


def paginate(request, queryset, per_page=DEFAULT_PAGE_SIZE, page_param="page"):
    """Retourne la page demandee, en retombant sur une page valide si besoin."""
    paginator = Paginator(queryset, per_page)
    return paginator.get_page(request.GET.get(page_param))


def querystring_without(request, *keys):
    """Querystring courante privee de certains parametres, pour les liens de page."""
    params = request.GET.copy()
    for key in keys:
        params.pop(key, None)
    encoded = params.urlencode()
    return f"{encoded}&" if encoded else ""


def safe_next_url(request, candidate_url, fallback):
    if candidate_url and url_has_allowed_host_and_scheme(
        url=candidate_url,
        allowed_hosts={request.get_host()},
        require_https=request.is_secure(),
    ):
        return candidate_url
    return resolve_url(fallback)
