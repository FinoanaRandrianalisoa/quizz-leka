import logging
import random
import string
import time

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


def _deliver(msg: EmailMultiAlternatives) -> None:
    """Envoie le message avec relance automatique sur erreur SMTP transitoire."""
    last_exc: Exception | None = None
    for attempt in range(EMAIL_MAX_RETRIES):
        try:
            msg.send(fail_silently=False)
            return
        except Exception as exc:  # noqa: BLE001
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
        msg = EmailMultiAlternatives(
            subject=subject,
            body=text_body,
            from_email=getattr(settings, "DEFAULT_FROM_EMAIL", None),
            to=[email],
        )
        msg.attach_alternative(html_body, "text/html")
        _deliver(msg)
        logger.info("Email de vérification envoyé à %s", email)
        return True
    except Exception as exc:
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
        msg = EmailMultiAlternatives(
            subject=subject,
            body=text_body,
            from_email=getattr(settings, "DEFAULT_FROM_EMAIL", None),
            to=[email],
        )
        msg.attach_alternative(html_body, "text/html")
        _deliver(msg)
        logger.info("Email de reset mot de passe envoyé à %s", email)
        return True
    except Exception as exc:
        logger.error("Échec envoi email reset à %s: %s", email, exc)
        return False