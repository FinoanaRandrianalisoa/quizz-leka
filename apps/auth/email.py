import logging
import random
import string

from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string
from django.utils import timezone

logger = logging.getLogger(__name__)


def generate_code(length: int = 6) -> str:
    return "".join(random.choice(string.digits) for _ in range(length))


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
        msg.send(fail_silently=False)
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
        msg.send(fail_silently=False)
        logger.info("Email de reset mot de passe envoyé à %s", email)
        return True
    except Exception as exc:
        logger.error("Échec envoi email reset à %s: %s", email, exc)
        return False
