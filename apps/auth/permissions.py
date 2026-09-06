import hashlib

from django.conf import settings
from django.utils import timezone

from common.graphql.errors import InvalidOtpError


def hash_code(code: str) -> str:
    return hashlib.sha256(code.encode()).hexdigest()


def verify_otp_for_user(otp_request, code: str):
    if otp_request.utilise or otp_request.expires_at < timezone.now():
        raise InvalidOtpError()
    if not hashlib.sha256(code.encode()).hexdigest() == otp_request.code_hash:
        raise InvalidOtpError()
