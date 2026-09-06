"""Registre central des codes d'erreur métier normalisés.

Chaque exception métier est définie ici, une seule fois, et utilisée par tous
les resolvers. Le handler GraphQL central (`common/graphql/errors.py`) convertit
ces exceptions en réponse `extensions.code` normalisée. Toute nouvelle erreur
métier doit être ajoutée à ce fichier avant utilisation.
"""


class DomainError(Exception):
    """Base de toutes les erreurs métier attendues (pas des bugs)."""

    code = "INTERNAL_ERROR"
    default_message = "Une erreur est survenue, veuillez réessayer."

    def __init__(self, message=None):
        self.message = message or self.default_message
        super().__init__(self.message)


# ---------------------------------------------------------------------------
# AUTH
# ---------------------------------------------------------------------------
class InvalidCredentialsError(DomainError):
    code = "AUTH_INVALID_CREDENTIALS"
    default_message = "Identifiants invalides."


class InvalidRefreshTokenError(DomainError):
    code = "AUTH_INVALID_REFRESH_TOKEN"
    default_message = "Session expirée, veuillez vous reconnecter."


class RevokedRefreshTokenError(DomainError):
    code = "AUTH_REVOKED_REFRESH_TOKEN"
    default_message = "Session révoquée, veuillez vous reconnecter."


class InvalidOtpError(DomainError):
    code = "AUTH_INVALID_OTP"
    default_message = "Code de vérification invalide ou expiré."


class EmailNotVerifiedError(DomainError):
    code = "AUTH_EMAIL_NOT_VERIFIED"
    default_message = "Adresse email non vérifiée."


class StepUpRequiredError(DomainError):
    code = "AUTH_STEP_UP_REQUIRED"
    default_message = "Vérification renforcée requise."


class PseudoAlreadyTakenError(DomainError):
    code = "AUTH_PSEUDO_ALREADY_TAKEN"
    default_message = "Ce pseudo est déjà utilisé."


class EmailAlreadyTakenError(DomainError):
    code = "AUTH_EMAIL_ALREADY_TAKEN"
    default_message = "Cette adresse email est déjà utilisée."


# ---------------------------------------------------------------------------
# WALLET
# ---------------------------------------------------------------------------
class InsufficientFundsError(DomainError):
    code = "WALLET_INSUFFICIENT_FUNDS"
    default_message = "Solde insuffisant pour effectuer cette opération."


class InvalidAmountError(DomainError):
    code = "WALLET_INVALID_AMOUNT"
    default_message = "Montant invalide."


class DuplicateIdempotencyKeyError(DomainError):
    code = "WALLET_IDEMPOTENCY_CONFLICT"
    default_message = "Cette opération a déjà été traitée."


class WithdrawalAlreadyPendingError(DomainError):
    code = "WALLET_WITHDRAWAL_PENDING"
    default_message = "Un retrait est déjà en cours, veuillez patienter."


class InvalidWebhookSignatureError(DomainError):
    code = "WALLET_INVALID_WEBHOOK_SIGNATURE"
    default_message = "Signature invalide."


class PinNotSetError(DomainError):
    code = "WALLET_PIN_NOT_SET"
    default_message = "Aucun PIN portefeuille n'est défini."


class PinMismatchError(DomainError):
    code = "WALLET_PIN_MISMATCH"
    default_message = "Pin de confirmation incorrect."


class InvalidPinError(DomainError):
    code = "WALLET_PIN_INVALID"
    default_message = "PIN portefeuille incorrect."


class WalletLockedError(DomainError):
    code = "WALLET_LOCKED"
    default_message = "Le portefeuille est verrouillé. Attendez la fin du verrouillage temporaire."


class WalletAutoLockedError(DomainError):
    code = "WALLET_AUTO_LOCKED"
    default_message = "Le portefeuille s'est verrouillé automatiquement après expiration."


class WalletAlreadyUnlockedError(DomainError):
    code = "WALLET_ALREADY_UNLOCKED"
    default_message = "Le portefeuille est déjà déverrouillé."


class WalletUnlockRequiredError(DomainError):
    code = "WALLET_UNLOCK_REQUIRED"
    default_message = "Déverrouillez votre portefeuille avec le PIN avant cette opération."


class RechargeLimitExceededError(DomainError):
    code = "WALLET_RECHARGE_LIMIT"
    default_message = "La recharge DEMO est limitée à une fois par jour."


class StakeTooLowError(DomainError):
    code = "WALLET_STAKE_TOO_LOW"
    default_message = "La mise minimum est de 100 Ar."


class DuplicateSettlementError(DomainError):
    code = "FINANCE_DUPLICATE_SETTLEMENT"
    default_message = "Ce match a déjà été réglé."


class SettlementPreparationError(DomainError):
    code = "FINANCE_SETTLEMENT_ERROR"
    default_message = "Le règlement du match est impossible dans son état actuel."


class AdminFinanceAccessDeniedError(DomainError):
    code = "FINANCE_ADMIN_ACCESS_DENIED"
    default_message = "Accès réservé aux administrateurs."


# ---------------------------------------------------------------------------
# BETTING
# ---------------------------------------------------------------------------
class BettingClosedError(DomainError):
    code = "BET_ALREADY_CLOSED"
    default_message = "Les paris sont clôturés pour ce match."


class SelfBettingError(DomainError):
    code = "BET_SELF_BETTING"
    default_message = "Vous ne pouvez pas parier sur un match où vous jouez."


class CollusionRiskError(DomainError):
    code = "BET_COLLUSION_RISK"
    default_message = "Cette mise est refusée par nos règles de sécurité."


# ---------------------------------------------------------------------------
# MATCH
# ---------------------------------------------------------------------------
class MatchNotFoundError(DomainError):
    code = "MATCH_NOT_FOUND"
    default_message = "Partie introuvable."


class MatchAlreadyStartedError(DomainError):
    code = "MATCH_ALREADY_STARTED"
    default_message = "La partie a déjà commencé."


class MatchFullError(DomainError):
    code = "MATCH_FULL"
    default_message = "La partie est complète."


class MatchNotJoinableError(DomainError):
    code = "MATCH_NOT_JOINABLE"
    default_message = "Cette partie ne peut pas être rejointe."


class NotYourTurnError(DomainError):
    code = "MATCH_NOT_YOUR_TURN"
    default_message = "Ce n'est pas votre tour."


class MatchAbandonedError(DomainError):
    code = "MATCH_ABANDONED"
    default_message = "La partie a été abandonnée."


# ---------------------------------------------------------------------------
# SOCIAL
# ---------------------------------------------------------------------------
class FriendRequestExistsError(DomainError):
    code = "SOCIAL_FRIEND_REQUEST_EXISTS"
    default_message = "Une demande d'ami existe déjà entre ces deux comptes."


class CannotSelfFriendError(DomainError):
    code = "SOCIAL_CANNOT_SELF_FRIEND"
    default_message = "Vous ne pouvez pas vous ajouter vous-même."


# ---------------------------------------------------------------------------
# VALIDATION
# ---------------------------------------------------------------------------
class ValidationError(DomainError):
    code = "VALIDATION_ERROR"
    default_message = "Données invalides."


class RateLimitedError(DomainError):
    """Dépassement de quota — doit contenir `retry_after`."""

    code = "RATE_LIMITED"
    default_message = "Trop de requêtes, veuillez réessayer plus tard."

    def __init__(self, retry_after=None, message=None):
        self.retry_after = retry_after
        super().__init__(message or self.default_message)


class PermissionDeniedError(DomainError):
    code = "PERMISSION_DENIED"
    default_message = "Vous n'avez pas les droits nécessaires."


class NotFoundError(DomainError):
    code = "NOT_FOUND"
    default_message = "Ressource introuvable."


ERROR_CODE_MAP = {cls.code: cls for cls in DomainError.__subclasses__()}
