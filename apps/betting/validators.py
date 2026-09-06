from apps.betting.services import _lien_familial
from common.graphql.errors import SelfBettingError, CollusionRiskError


def verifier_anti_fraude(utilisateur, match, joueur_pari):
    """Contrôles bloquants anti-fraude avant placement de pari (RG-BET)."""
    if utilisateur.pk == match.joueur_hote_id or utilisateur.pk == match.joueur_invite_id:
        raise SelfBettingError()
    if joueur_pari == utilisateur:
        raise SelfBettingError()
    if _lien_familial(utilisateur, joueur_pari):
        raise CollusionRiskError()