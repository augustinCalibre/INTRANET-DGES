import ipaddress
from urllib.parse import urlparse, urlunparse

from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.http import HttpResponseRedirect
from django.shortcuts import redirect


def home(request):
    if request.user.is_authenticated:
        return redirect("dashboard:home")
    return redirect("accounts:login")


def _is_ip_host(hostname):
    normalized_host = (hostname or "").split(":", 1)[0].strip("[]")
    try:
        ipaddress.ip_address(normalized_host)
        return True
    except ValueError:
        return False


def _build_messaging_fallback_url(request_host):
    configured_fallback_url = settings.MESSAGING_FALLBACK_URL
    if configured_fallback_url:
        return configured_fallback_url

    parsed_url = urlparse(settings.MESSAGING_URL)
    scheme = parsed_url.scheme or "https"
    port = parsed_url.port or (8443 if scheme == "https" else 80)
    return urlunparse(parsed_url._replace(netloc=f"{request_host}:{port}"))


@login_required
def messaging_redirect(request):
    current_host = request.get_host().split(":", 1)[0]
    if _is_ip_host(current_host):
        return HttpResponseRedirect(_build_messaging_fallback_url(current_host))
    return HttpResponseRedirect(settings.MESSAGING_URL)
