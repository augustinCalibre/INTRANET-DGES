from datetime import datetime
from urllib.parse import urlparse

from django.conf import settings


def _dedupe_urls(*urls):
    unique_urls = []
    seen = set()
    for url in urls:
        if not url or url in seen:
            continue
        seen.add(url)
        unique_urls.append(url)
    return unique_urls


def application_context(request):
    intranet_url = settings.INTRANET_URL
    intranet_host = urlparse(intranet_url).netloc or intranet_url
    intranet_fallback_url = settings.INTRANET_FALLBACK_URL
    intranet_access_urls = _dedupe_urls(intranet_url, intranet_fallback_url)
    messaging_url = settings.MESSAGING_URL
    messaging_host = urlparse(messaging_url).netloc or messaging_url
    messaging_fallback_url = settings.MESSAGING_FALLBACK_URL
    next_meeting = None
    next_meeting_countdown = ""
    unread_meeting_notifications_count = 0
    can_schedule_meeting = False
    can_manage_documents = False
    can_manage_visitors = False
    can_manage_diplomas = False
    can_access_courriers = False
    can_access_bordereaux = False
    can_view_accounts = False
    can_manage_backups = False
    lots_awaiting_signature_count = 0
    courriers_a_traiter_count = 0
    bordereaux_en_attente_count = 0
    nouveaux_documents_count = 0

    if getattr(request.user, "is_authenticated", False):
        from core.models import Notification
        from core.permissions import can_manage_documents as user_can_manage_documents
        from core.permissions import can_access_diplomas as user_can_manage_diplomas
        from core.permissions import can_manage_meetings, can_validate_as_dg
        from core.permissions import can_manage_backups as user_can_manage_backups
        from core.permissions import can_view_accounts as user_can_view_accounts
        from core.permissions import can_manage_visitors as user_can_manage_visitors
        from core.permissions import can_access_courriers as user_can_access_courriers
        from core.permissions import can_access_bordereaux as user_can_access_bordereaux
        from bordereaux.selectors import get_bordereaux_en_attente
        from documents.services import get_documents_non_lus
        from courriers.selectors import (
            get_courriers_awaiting_dg,
            get_courriers_awaiting_secretariat,
        )
        from diplomas.selectors import get_lots_awaiting_signature
        from meetings.selectors import get_next_meeting_for_user
        from meetings.services import build_countdown_label, dispatch_due_meeting_reminders

        dispatch_due_meeting_reminders()
        next_meeting = get_next_meeting_for_user(request.user)
        next_meeting_countdown = build_countdown_label(next_meeting)
        unread_meeting_notifications_count = Notification.objects.filter(
            utilisateur=request.user,
            type_notification=Notification.Type.MEETING,
            lu=False,
        ).count()
        can_schedule_meeting = can_manage_meetings(request.user)
        can_manage_documents = user_can_manage_documents(request.user)
        # Tout agent peut recevoir un document, y compris sans droit de depot :
        # le compteur ne depend d'aucune capacite.
        nouveaux_documents_count = get_documents_non_lus(request.user).count()
        can_manage_visitors = user_can_manage_visitors(request.user)
        can_manage_diplomas = user_can_manage_diplomas(request.user)
        if can_manage_diplomas:
            lots_awaiting_signature_count = get_lots_awaiting_signature(request.user).count()

        can_access_bordereaux = user_can_access_bordereaux(request.user)
        if can_access_bordereaux:
            # Le badge compte les dossiers dont l'engagement n'est pas signe :
            # ce sont eux qui n'ont pas encore commence leur circuit.
            bordereaux_en_attente_count = get_bordereaux_en_attente(request.user).count()

        can_view_accounts = user_can_view_accounts(request.user)
        can_manage_backups = user_can_manage_backups(request.user)
        can_access_courriers = user_can_access_courriers(request.user)
        if can_access_courriers:
            # Le badge compte ce qui attend une action de cet utilisateur :
            # le DG voit les courriers a viser, le secretariat ceux a transmettre.
            if can_validate_as_dg(request.user):
                courriers_a_traiter_count = get_courriers_awaiting_dg(request.user).count()
            else:
                courriers_a_traiter_count = get_courriers_awaiting_secretariat(request.user).count()

    return {
        "app_name": "Intranet DGES",
        "asset_version": settings.ASSET_VERSION,
        "current_year": datetime.now().year,
        "intranet_url": intranet_url,
        "intranet_host": intranet_host,
        "intranet_fallback_url": intranet_fallback_url,
        "intranet_access_urls": intranet_access_urls,
        "messaging_url": messaging_url,
        "messaging_host": messaging_host,
        "messaging_fallback_url": messaging_fallback_url,
        "next_meeting": next_meeting,
        "next_meeting_countdown": next_meeting_countdown,
        "unread_meeting_notifications_count": unread_meeting_notifications_count,
        "can_schedule_meeting": can_schedule_meeting,
        "can_manage_documents": can_manage_documents,
        "can_manage_visitors": can_manage_visitors,
        "can_manage_diplomas": can_manage_diplomas,
        "can_access_courriers": can_access_courriers,
        "can_access_bordereaux": can_access_bordereaux,
        "can_view_accounts": can_view_accounts,
        "can_manage_backups": can_manage_backups,
        "lots_awaiting_signature_count": lots_awaiting_signature_count,
        "courriers_a_traiter_count": courriers_a_traiter_count,
        "bordereaux_en_attente_count": bordereaux_en_attente_count,
        "nouveaux_documents_count": nouveaux_documents_count,
    }
