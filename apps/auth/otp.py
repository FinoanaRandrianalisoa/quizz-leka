import random
import string

from django.conf import settings


def generate_otp(length: int = 6) -> str:
    return "".join(random.choice(string.digits) for _ in range(length))


def send_otp(phone_number: str, code: str) -> None:
    """Envoi OTP via fournisseur SMS. Fonction d'interface — provider réel à brancher.

    En dev, on logge le code ; en prod, intégration Twilio / Africa's Talking.
    """
    # Placeholder : intégrer le provider OTP ici.
    import logging

    logger = logging.getLogger(__name__)
    logger.info("OTP envoyé vers %s: %s", phone_number[-4:], code)
