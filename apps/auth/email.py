import json
import logging
import random
import string
import time
import urllib.error
import urllib.request

from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string
from django.utils import timezone

logger = logging.getLogger(__name__)

# Codes de réponse SMTP temporaires (limite de débit, file occupée…).
# Voir RFC 5321 : 4xx = échec temporaire, il faut réessayer.
_TRANSIENT_CODES = {420, 421, 450, 451, 452}

# Nombre de tentatives et délai (secondes) entre deux essais.
EMAIL_MAX_RETRIES = 3
EMAIL_RETRY_DELAYS = (2, 5)

# Resend (API HTTPS) — obligatoire sur Railway où le SMTP sortant est bloqué.
RESEND_API_URL = "https://api.resend.com/emails"
RESEND_TIMEOUT = 30


def generate_code(length: int = 6) -> str:
    return "".join(random.choice(string.digits) for _ in range(length))


def _is_transient_smtp_error(exc: Exception) -> bool:
    """True si l'erreur SMTP est temporaire et peut être retentée."""
    if not hasattr(exc, "smtp_code") or exc.smtp_code is None:
        return False
    try:
        return int(exc.smtp_code) in _TRANSIENT_CODES
    except (TypeError, ValueError):
        return False


def _deliver_smtp(subject: str, text_body: str, html_body: str, to_email: str) -> None:
    """Envoie via SMTP avec relance automatique sur erreur transitoire."""
    msg = EmailMultiAlternatives(
        subject=subject,
        body=text_body,
        from_email=getattr(settings, "DEFAULT_FROM_EMAIL", None),
        to=[to_email],
    )
    msg.attach_alternative(html_body, "text/html")
    last_exc: Exception | None = None
    for attempt in range(EMAIL_MAX_RETRIES):
        try:
            msg.send(fail_silently=False)
            return
        except Exception as exc:
            last_exc = exc
            if not _is_transient_smtp_error(exc) or attempt == EMAIL_MAX_RETRIES - 1:
                raise
            delay = EMAIL_RETRY_DELAYS[attempt]
            logger.warning(
                "Erreur SMTP transitoire (%s), nouvelle tentative dans %ss "
                "(essaie %d/%d)",
                exc,
                delay,
                attempt + 2,
                EMAIL_MAX_RETRIES,
            )
            time.sleep(delay)
    if last_exc is not None:
        raise last_exc


def _deliver_resend(subject: str, text_body: str, html_body: str, to_email: str) -> None:
    """Envoie via l'API HTTPS Resend (port 443, jamais bloqué par Railway)."""
    api_key = getattr(settings, "RESEND_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("RESEND_API_KEY non configurée")
    payload = {
        "from": getattr(settings, "DEFAULT_FROM_EMAIL", None) or "onboarding@resend.dev",
        "to": [to_email],
        "subject": subject,
        "text": text_body,
        "html": html_body,
    }
    request = urllib.request.Request(
        RESEND_API_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    last_exc: Exception | None = None
    for attempt in range(EMAIL_MAX_RETRIES):
        try:
            with urllib.request.urlopen(request, timeout=RESEND_TIMEOUT) as resp:
                if 200 <= resp.status < 300:
                    return
                last_exc = RuntimeError(f"Resend HTTP {resp.status}")
        except urllib.error.HTTPError as exc:
            last_exc = exc
            if attempt == EMAIL_MAX_RETRIES - 1:
                raise
            if exc.code not in (408, 409, 429) and exc.code < 500:
                raise
        except Exception as exc:  # erreur réseau transitoire
            last_exc = exc
            if attempt == EMAIL_MAX_RETRIES - 1:
                raise
        delay = EMAIL_RETRY_DELAYS[attempt]
        logger.warning(
            "Resend : échec temporaire (%s), nouvelle tentative dans %ss "
            "(essaie %d/%d)",
            last_exc,
            delay,
            attempt + 2,
            EMAIL_MAX_RETRIES,
        )
        time.sleep(delay)
    if last_exc is not None:
        raise last_exc


def _deliver(subject: str, text_body: str, html_body: str, to_email: str) -> None:
    """Utilise Resend en priorité (production), sinon SMTP (développement)."""
    if getattr(settings, "RESEND_API_KEY", "").strip():
        _deliver_resend(subject, text_body, html_body, to_email)
    else:
        _deliver_smtp(subject, text_body, html_body, to_email)


def send_verification_email(email: str, pseudo: str, code: str) -> bool:
    """Envoie un email de vérification avec le code."""
    subject = "Quizz Leka - Vérifiez votre adresse email"
    context = {
        "pseudo": pseudo,
        "code": code,
        "expiry_minutes": getattr(settings, "EMAIL_VERIFICATION_TTL", 900) // 60,
        "year": timezone.now().year,
    }
    html_body = render_to_string("auth/email_verification.html", context)
    text_body = (
        f"Bonjour {pseudo},\n\n"
        f"Voici votre code de vérification : {code}\n"
        f"Ce code expire dans {context['expiry_minutes']} minutes.\n\n"
        f"Si vous n'avez pas demandé cette vérification, ignorez cet email."
    )
    try:
        _deliver(subject, text_body, html_body, email)
        logger.info("Email de vérification envoyé à %s", email)
        return True
    except Exception as exc:  # noqa: BLE001 — renvoie False, l'appelant gère
        logger.error("Échec envoi email vérification à %s: %s", email, exc)
        return False


def send_password_reset_email(email: str, pseudo: str, code: str) -> bool:
    """Envoie un email de réinitialisation de mot de passe avec le code."""
    subject = "Quizz Leka - Réinitialisation du mot de passe"
    context = {
        "pseudo": pseudo,
        "code": code,
        "expiry_minutes": getattr(settings, "PASSWORD_RESET_TTL", 900) // 60,
        "year": timezone.now().year,
    }
    html_body = render_to_string("auth/password_reset.html", context)
    text_body = (
        f"Bonjour {pseudo},\n\n"
        f"Voici votre code de réinitialisation : {code}\n"
        f"Ce code expire dans {context['expiry_minutes']} minutes.\n\n"
        f"Si vous n'avez pas demandé cette réinitialisation, changez immédiatement votre mot de passe."
    )
    try:
        _deliver(subject, text_body, html_body, email)
        logger.info("Email de reset mot de passe envoyé à %s", email)
        return True
    except Exception as exc:  # noqa: BLE001 — renvoie False, l'appelant gère
        logger.error("Échec envoi email reset à %s: %s", email, exc)
        return False