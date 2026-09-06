import logging
import threading
import time
import uuid

from decimal import Decimal

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.db import transaction
from django.utils import timezone
from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer

from apps.matches.models import Match, Tour, ReponseTour, Participation
from apps.social.models import Notification
from apps.social.services import envoyer_notification
from apps.themes.models import Question, Reponse, Theme
from apps.wallet import services as wallet_services
from common.graphql.errors import (
    MatchNotFoundError,
    MatchFullError,
    MatchNotJoinableError,
    MatchAlreadyStartedError,
    PermissionDeniedError,
    NotFoundError,
    ValidationError,
    InsufficientFundsError,
    StakeTooLowError,
)

logger = logging.getLogger(__name__)


class RpsStateStore(dict):
    """Proxy dict backed by Django cache with a local-memory fallback when Redis is unavailable."""

    def __init__(self, prefix: str, ttl: int = 3600):
        self.prefix = prefix
        self.ttl = ttl
        self._memory = {}

    def _index_key(self) -> str:
        return f"rps:{self.prefix}:index"

    def _entry_key(self, key: str) -> str:
        return f"rps:{self.prefix}:{key}"

    def _cache_get(self, key: str, default=None):
        try:
            return cache.get(key, default)
        except Exception:
            return self._memory.get(key, default)

    def _cache_set(self, key: str, value, timeout: int | None = None) -> None:
        try:
            cache.set(key, value, timeout=timeout)
        except Exception:
            self._memory[key] = value

    def _cache_delete(self, key: str) -> None:
        try:
            cache.delete(key)
        except Exception:
            self._memory.pop(key, None)

    def _keys(self) -> list[str]:
        ids = self._cache_get(self._index_key()) or []
        valid_ids = []
        for item in ids:
            value = self._cache_get(self._entry_key(str(item)))
            if value is not None:
                valid_ids.append(str(item))
        return valid_ids

    def __getitem__(self, key):
        value = self._cache_get(self._entry_key(str(key)))
        if value is None:
            raise KeyError(key)
        return value

    def __setitem__(self, key, value):
        cache_key = self._entry_key(str(key))
        self._cache_set(cache_key, value, timeout=self.ttl)
        ids = self._keys()
        if str(key) not in ids:
            ids.append(str(key))
            self._cache_set(self._index_key(), ids, timeout=self.ttl)

    def __delitem__(self, key):
        self._cache_delete(self._entry_key(str(key)))
        ids = [item for item in self._keys() if item != str(key)]
        self._cache_set(self._index_key(), ids, timeout=self.ttl)

    def __contains__(self, key):
        return self._cache_get(self._entry_key(str(key))) is not None

    def get(self, key, default=None):
        try:
            return self[key]
        except KeyError:
            return default

    def keys(self):
        return self._keys()

    def values(self):
        return [self._cache_get(self._entry_key(item)) for item in self._keys() if self._cache_get(self._entry_key(item)) is not None]

    def items(self):
        return [(item, self._cache_get(self._entry_key(item))) for item in self._keys() if self._cache_get(self._entry_key(item)) is not None]

    def clear(self):
        for item in self._keys():
            self._cache_delete(self._entry_key(item))
        self._cache_delete(self._index_key())
        self._memory.clear()

    def __len__(self):
        return len(self._keys())

    def __iter__(self):
        return iter(self._keys())


RPS_CHALLENGES: dict[str, dict] = RpsStateStore("challenge", ttl=3600)
RPS_MATCHES: dict[str, dict] = RpsStateStore("match", ttl=86400)

PENALTY_CHALLENGES: dict[str, dict] = RpsStateStore("penalty_challenge", ttl=3600)
PENALTY_MATCHES: dict[str, dict] = RpsStateStore("penalty_match", ttl=86400)


def _rps_winner(coup_a: str, coup_b: str) -> str | None:
    if coup_a == coup_b:
        return None
    if {coup_a, coup_b} not in ({"pierre", "papier"}, {"papier", "ciseaux"}, {"ciseaux", "pierre"}):
        return None
    beats = {"pierre": "ciseaux", "ciseaux": "papier", "papier": "pierre"}
    return coup_a if beats[coup_a] == coup_b else coup_b


def _broadcast(match_id: int, data: dict) -> None:
    try:
        layer = get_channel_layer()
        async_to_sync(layer.group_send)(f"match_{match_id}", {"type": "match.event", "data": data})
    except Exception:  # pragma: no cover - canal indisponible (tests, dev sans Redis)
        logger.warning("Impossible de diffuser l'événement du match %s", match_id)


def _broadcast_rps_match(match_id: str, match: dict) -> None:
    try:
        layer = get_channel_layer()
        async_to_sync(layer.group_send)(
            f"rps_{match_id}",
            {
                "type": "rps.event",
                "data": {
                    "type": "rps.update",
                    "match": match,
                },
            },
        )
    except Exception:
        logger.warning("Impossible de diffuser l'événement RPS du match %s", match_id)


def _mise_reference(match: Match, utilisateur) -> str:
    return f"mise-match-{match.pk}-{utilisateur.pk}"


def _valider_mise(montant: Decimal, portefeuille) -> Decimal:
    """Validations serveur : minimum configurable et maximum = solde disponible."""
    montant = Decimal(str(montant))
    if montant < 0:
        raise InsufficientFundsError()
    if montant == 0:
        return montant
    if montant < Decimal(str(settings.DEMO_STAKE_MIN)):
        raise StakeTooLowError()
    if montant > portefeuille.solde_recharge:
        raise InsufficientFundsError()
    return montant


def _ouvrir_tour(match: Match) -> Tour:
    deja_utilisees = Tour.objects.filter(match=match).values_list("question_id", flat=True)
    question = (
        Question.objects.filter(theme=match.theme, validee=True)
        .exclude(pk__in=list(deja_utilisees))
        .order_by("?")
        .first()
    )
    if not question:
        raise ValidationError("Aucune question disponible pour ce thème.")
    tour = Tour.objects.create(match=match, numero=match.tour_actuel + 1, question=question)
    match.tour_actuel = tour.numero
    match.save(update_fields=["tour_actuel"])
    # Start a background timer to expire the tour after 5 seconds if no answers are submitted.
    try:
        timer_seconds = getattr(match, "question_duration_seconds", 5)
    except Exception:
        timer_seconds = 5

    def _expire_check(tour_id: int, delay: int):
        time.sleep(delay)
        try:
            t = Tour.objects.select_related("match").get(pk=tour_id)
        except Tour.DoesNotExist:
            return
        # If still in progress and no responses, mark as finished and open next
        if t.statut == Tour.Statut.EN_COURS and not t.reponses.exists():
            with transaction.atomic():
                t.statut = Tour.Statut.TERMINE
                t.save(update_fields=["statut"])
                m = t.match
                # similar to soumettre_reponse: open next round or finish
                defaite_instantanee = False
                fin = (
                    defaite_instantanee
                    or m.score_hote >= m.score_cible
                    or m.score_invite >= m.score_cible
                )
                if fin:
                    _cloturer(m, defaite_instantanee)
                    _broadcast(m.pk, {"type": "match.over", "match_id": m.pk, "vainqueur_id": m.vainqueur_id})
                else:
                    m.save(update_fields=["score_hote", "score_invite"])  # no score change
                    suivant = _ouvrir_tour(m)
                    _broadcast(
                        m.pk,
                        {
                            "type": "match.round",
                            "match_id": m.pk,
                            "tour_id": suivant.pk,
                            "question_id": suivant.question_id,
                            "score_hote": m.score_hote,
                            "score_invite": m.score_invite,
                        },
                    )

    threading.Thread(target=_expire_check, args=(tour.pk, timer_seconds), daemon=True).start()
    return tour


def creer_partie(utilisateur, theme_id: int, mise, score_cible: int = 8, type_jeu: str = "classique") -> Match:
    type_jeu = (type_jeu or "classique").strip()
    if score_cible < 1:
        raise ValidationError("Le score cible doit être positif.")
    if not hasattr(utilisateur, "portefeuille"):
        raise ValidationError("Portefeuille introuvable.")

    mise = _valider_mise(mise, utilisateur.portefeuille)

    if type_jeu == Match.TypeJeu.COURSE_LAPIN:
        theme, _ = Theme.objects.get_or_create(
            slug="course-lapin",
            defaults={
                "nom": "Course lapin",
                "description": "Course de lapin multijoueur",
                "category": "course lapin",
                "icone": "🐰",
            },
        )
    else:
        theme = Theme.objects.filter(pk=theme_id).first()
        if not theme or not Question.objects.filter(theme_id=theme.id, validee=True).exists():
            raise NotFoundError("Thème introuvable ou sans questions validées.")

    with transaction.atomic():
        match = Match.objects.create(
            type_jeu=type_jeu,
            theme=theme,
            mise=mise,
            mise_proposee_invite=None,
            score_cible=score_cible,
            joueur_hote=utilisateur,
        )
        if match.mise > 0:
            wallet_services.bloquer_mise(
                utilisateur.portefeuille,
                match.mise,
                reference=_mise_reference(match, utilisateur),
                metadata={"match": match.pk, "role": "hote"},
                idempotency_key=f"reserve:{match.pk}:{utilisateur.pk}",
            )

        if type_jeu != Match.TypeJeu.COURSE_LAPIN:
            for target_user in get_user_model().objects.exclude(pk=utilisateur.pk):
                envoyer_notification(
                    target_user,
                    Notification.Type.SYSTEME,
                    "Nouvelle partie créée",
                    f"{utilisateur.pseudo} a créé une partie {theme.nom}. Rejoins-la dès maintenant.",
                    reference_id=match.pk,
                    expediteur=utilisateur,
                )

        try:
            layer = get_channel_layer()
            async_to_sync(layer.group_send)(
                "parties",
                {
                    "type": "parties.event",
                    "data": {
                        "type": "match.created",
                        "match": {
                            "id": match.pk,
                            "statut": match.statut,
                            "scoreCible": match.score_cible,
                            "typeJeu": match.type_jeu,
                            "joueurHote": {"pseudo": match.joueur_hote.pseudo},
                            "theme": {"id": match.theme_id, "nom": getattr(match.theme, "nom", "")},
                        },
                    },
                },
            )
        except Exception:
            logger.debug("channel layer not available for parties broadcast")
    return match


def rejoindre_partie(utilisateur, match_id: int, mise=None) -> Match:
    with transaction.atomic():
        try:
            match = Match.objects.select_for_update().get(pk=match_id)
        except Match.DoesNotExist:
            raise MatchNotFoundError()
        if match.complet:
            raise MatchFullError()
        if match.statut != Match.Statut.EN_ATTENTE:
            raise MatchNotJoinableError()
        if match.joueur_hote == utilisateur:
            raise MatchNotJoinableError("Vous ne pouvez pas rejoindre votre propre partie.")
        if not hasattr(utilisateur, "portefeuille"):
            raise ValidationError("Portefeuille introuvable.")

        eff = Decimal("0")
        if match.mise > 0:
            proposition = match.mise if mise is None else Decimal(str(mise))
            proposition = _valider_mise(proposition, utilisateur.portefeuille)
            match.mise_proposee_invite = proposition
        else:
            match.mise_proposee_invite = Decimal("0")

        match.joueur_invite = utilisateur
        match.statut = Match.Statut.EN_COURS
        match.commence_le = timezone.now()
        match.save()
        Participation.objects.get_or_create(match=match, utilisateur=match.joueur_hote, defaults={"score_final": 0})
        Participation.objects.get_or_create(match=match, utilisateur=utilisateur, defaults={"score_final": 0})

        if match.mise > 0:
            proposition = match.mise_proposee_invite
            wallet_services.bloquer_mise(
                utilisateur.portefeuille,
                proposition,
                reference=_mise_reference(match, utilisateur),
                metadata={"match": match.pk, "role": "invite"},
                idempotency_key=f"reserve:{match.pk}:{utilisateur.pk}",
            )
            eff = match.mise_effective
            # Libération des surplus au-delà de la mise effective (jamais déduits).
            surplus_hote = match.mise - eff
            if surplus_hote > 0:
                wallet_services.liberer_mise(
                    match.joueur_hote.portefeuille,
                    surplus_hote,
                    reference=f"surplus-{match.pk}-{match.joueur_hote.pk}",
                    metadata={"match": match.pk, "role": "hote", "type_de_surplus": "mise"},
                    idempotency_key=f"surplus:{match.pk}:{match.joueur_hote.pk}",
                )
            surplus_invite = proposition - eff
            if surplus_invite > 0:
                wallet_services.liberer_mise(
                    utilisateur.portefeuille,
                    surplus_invite,
                    reference=f"surplus-{match.pk}-{utilisateur.pk}",
                    metadata={"match": match.pk, "role": "invite", "type_de_surplus": "mise"},
                    idempotency_key=f"surplus:{match.pk}:{utilisateur.pk}",
                )
            # Engagement (définitif) de la mise effective des deux joueurs.
            wallet_services.engager_mise(
                match.joueur_hote.portefeuille,
                eff,
                reference=f"engage-match-{match.pk}-{match.joueur_hote.pk}",
                metadata={"match": match.pk},
            )
            wallet_services.engager_mise(
                utilisateur.portefeuille,
                eff,
                reference=f"engage-match-{match.pk}-{utilisateur.pk}",
                metadata={"match": match.pk},
            )

        if match.type_jeu == Match.TypeJeu.COURSE_LAPIN:
            tour = None
        else:
            tour = _ouvrir_tour(match)

    if match.type_jeu == Match.TypeJeu.COURSE_LAPIN:
        _broadcast(
            match.pk,
            {
                "type": "match.start",
                "match_id": match.pk,
                "joueurs": [match.joueur_hote.pseudo, utilisateur.pseudo],
                "score_cible": match.score_cible,
                "type_jeu": match.type_jeu,
            },
        )
        return match

    _broadcast(
        match.pk,
        {
            "type": "match.start",
            "match_id": match.pk,
            "joueurs": [match.joueur_hote.pseudo, utilisateur.pseudo],
            "tour_id": tour.pk,
            "question_id": tour.question_id,
            "score_cible": match.score_cible,
        },
    )
    return match


def soumettre_reponse(utilisateur, tour_id: int, reponse_id: int, duree_ms: int = 0) -> bool:
    try:
        tour = Tour.objects.select_related("match", "question").get(pk=tour_id)
    except Tour.DoesNotExist:
        raise MatchNotFoundError()
    match = tour.match
    if match.statut != Match.Statut.EN_COURS:
        raise MatchAlreadyStartedError("La partie est déjà terminée.")
    if utilisateur.pk not in (match.joueur_hote_id, match.joueur_invite_id):
        raise PermissionDeniedError("Vous ne participez pas à cette partie.")
    if ReponseTour.objects.filter(tour=tour, utilisateur=utilisateur).exists():
        return True

    reponse = Reponse.objects.filter(pk=reponse_id, question=tour.question).first()
    if not reponse:
        raise NotFoundError("Réponse invalide.")
    correcte = reponse.est_correcte

    with transaction.atomic():
        ReponseTour.objects.create(
            tour=tour,
            utilisateur=utilisateur,
            reponse=reponse,
            correcte=correcte,
            duree_ms=duree_ms,
        )
        est_hote = match.joueur_hote_id == utilisateur.pk
        if correcte:
            if est_hote:
                match.score_hote += 1
            else:
                match.score_invite += 1
        tour.statut = Tour.Statut.TERMINE
        tour.save(update_fields=["statut"])

        defaite_instantanee = match.type_jeu == Match.TypeJeu.INTRUS and not correcte
        fin = (
            defaite_instantanee
            or match.score_hote >= match.score_cible
            or match.score_invite >= match.score_cible
        )

        if fin:
            _cloturer(match, defaite_instantanee)
            _broadcast(match.pk, {"type": "match.over", "match_id": match.pk, "vainqueur_id": match.vainqueur_id})
        else:
            match.save(update_fields=["score_hote", "score_invite"])
            suivant = _ouvrir_tour(match)
            _broadcast(
                match.pk,
                {
                    "type": "match.round",
                    "match_id": match.pk,
                    "tour_id": suivant.pk,
                    "question_id": suivant.question_id,
                    "score_hote": match.score_hote,
                    "score_invite": match.score_invite,
                },
            )
    return True


def _sync_match(source: Match, cible: Match) -> None:
    """Rejoue les champs modifiés du règlement sur l'instance du caller."""
    for champ in ("vainqueur_id", "statut", "termine_le", "score_hote", "score_invite"):
        setattr(cible, champ, getattr(source, champ))


def _cloturer(match: Match, defaite_instantanee: bool) -> None:
    with transaction.atomic():
        m = (
            Match.objects.select_for_update()
            .select_related("joueur_hote__portefeuille", "joueur_invite__portefeuille")
            .get(pk=match.pk)
        )
        # Garde anti double règlement : un match clos n'est jamais réglé deux fois.
        if m.statut != Match.Statut.EN_COURS:
            return

        eff = m.mise_effective

        if m.type_jeu == Match.TypeJeu.INTRUS and defaite_instantanee:
            # L'« intrus » : celui qui répond faux perd immédiatement.
            dernier_joueur = (
                ReponseTour.objects.filter(tour=m.tours.last()).values_list("utilisateur_id", flat=True).last()
            )
            perdant_id = dernier_joueur
            vainqueur_id = m.joueur_invite_id if perdant_id == m.joueur_hote_id else m.joueur_hote_id
        elif m.score_hote == m.score_invite:
            m.statut = Match.Statut.ANNULE
            m.termine_le = timezone.now()
            m.save()
            if m.mise > 0:
                for joueur in (m.joueur_hote, m.joueur_invite):
                    if joueur and hasattr(joueur, "portefeuille"):
                        wallet_services.liberer_mise(
                            joueur.portefeuille,
                            eff,
                            type_=wallet_services.LedgerEntry.Type.REMBOURSEMENT,
                            reference=f"egalite-{m.pk}-{joueur.pk}",
                            metadata={"match": m.pk},
                            idempotency_key=f"settle:{m.pk}:egalite:{joueur.pk}",
                        )
            _sync_match(m, match)
            _broadcast(m.pk, {"type": "match.over", "match_id": m.pk, "annule": True})
            return
        else:
            perdant_id = m.joueur_invite_id if m.score_hote > m.score_invite else m.joueur_hote_id
            vainqueur_id = m.joueur_hote_id if perdant_id == m.joueur_invite_id else m.joueur_invite_id

        m.vainqueur_id = vainqueur_id
        m.statut = Match.Statut.TERMINE
        m.termine_le = timezone.now()
        m.save()
        Participation.objects.filter(match=m, utilisateur_id=vainqueur_id).update(score_final=1, vainqueur=True)
        Participation.objects.filter(match=m, utilisateur_id=perdant_id).update(score_final=0, vainqueur=False)

        if m.mise > 0 and vainqueur_id:
            gagnant_pf = (
                m.joueur_hote.portefeuille if m.joueur_hote_id == vainqueur_id else m.joueur_invite.portefeuille
            )
            perdant_pf = (
                m.joueur_hote.portefeuille if m.joueur_hote_id == perdant_id else m.joueur_invite.portefeuille
            )
            if gagnant_pf and perdant_pf:
                wallet_services.GameSettlementService.regler_duel(
                    portefeuille_gagnant=gagnant_pf,
                    portefeuille_perdant=perdant_pf,
                    mise_effective=eff,
                    reference=f"match-{m.pk}",
                    metadata={"match": m.pk},
                )

    _sync_match(m, match)

    try:
        from apps.betting.tasks import resoudre_paris_match

        resoudre_paris_match.delay(m.pk)
    except Exception:  # pragma: no cover
        logger.warning("Résolution des paris non déclenchée pour le match %s", m.pk)


def annuler_partie(utilisateur, match_id: int) -> bool:
    with transaction.atomic():
        try:
            match = Match.objects.select_for_update().get(pk=match_id)
        except Match.DoesNotExist:
            raise NotFoundError("Match introuvable.")
        if match.joueur_hote != utilisateur:
            raise PermissionDeniedError("Vous n'êtes pas l'hôte de cette partie.")
        if match.statut != Match.Statut.EN_ATTENTE:
            raise ValidationError("Impossible d'annuler une partie déjà commencée.")

        match.statut = Match.Statut.ANNULE
        match.save(update_fields=["statut"])
        if match.mise > 0:
            for joueur in (match.joueur_hote, match.joueur_invite):
                if joueur and hasattr(joueur, "portefeuille"):
                    wallet_services.liberer_mise(
                        joueur.portefeuille,
                        match.mise,
                        type_=wallet_services.LedgerEntry.Type.REMBOURSEMENT,
                        reference=f"remboursement-{match.pk}-{joueur.pk}",
                        metadata={"match": match.pk},
                        idempotency_key=f"annulation:{match.pk}:{joueur.pk}",
                    )

    _broadcast(match.pk, {"type": "match.over", "match_id": match.pk, "annule": True})
    return True


def inviter_joueur_course_lapin(utilisateur, match_id: int, invite_id: int) -> Match:
    if invite_id == utilisateur.pk:
        raise ValidationError("Vous ne pouvez pas vous inviter vous-même.")

    try:
        match = Match.objects.select_related("theme", "joueur_hote", "joueur_invite").get(pk=match_id)
    except Match.DoesNotExist:
        raise MatchNotFoundError()

    if match.type_jeu != Match.TypeJeu.COURSE_LAPIN:
        raise ValidationError("Cette invitation n'est valide que pour une partie Course lapin.")
    if match.joueur_hote_id != utilisateur.pk:
        raise PermissionDeniedError("Vous n'êtes pas l'hôte de cette partie.")
    if match.joueur_invite_id and match.joueur_invite_id != invite_id:
        raise MatchFullError()

    invite = get_user_model().objects.filter(pk=invite_id).first()
    if not invite:
        raise NotFoundError("Joueur introuvable.")

    if match.statut != Match.Statut.EN_ATTENTE:
        raise MatchAlreadyStartedError("La partie a déjà commencé.")
    if match.joueur_invite_id == invite_id:
        return match

    match.joueur_invite = invite
    match.commence_le = None
    match.save(update_fields=["joueur_invite", "commence_le"])
    envoyer_notification(
        invite,
        Notification.Type.DEFI_RECU,
        "Invitation Course lapin",
        f"{utilisateur.pseudo} vous invite à rejoindre sa partie Course lapin. Acceptez pour entrer dans le lobby et attendre le lancement.",
        reference_id=match.pk,
        expediteur=utilisateur,
    )
    _broadcast(
        match.pk,
        {
            "type": "rabbit.invite_sent",
            "match_id": match.pk,
            "invite_id": invite.pk,
            "invite_pseudo": invite.pseudo,
            "statut": match.statut,
        },
    )
    return match


def accepter_invitation_course_lapin(utilisateur, match_id: int) -> Match:
    with transaction.atomic():
        try:
            match = Match.objects.select_for_update().select_related("theme", "joueur_hote", "joueur_invite").get(pk=match_id)
        except Match.DoesNotExist:
            raise MatchNotFoundError()

        if match.type_jeu != Match.TypeJeu.COURSE_LAPIN:
            raise ValidationError("Cette invitation n'est pas une partie Course lapin.")
        if match.joueur_hote_id == utilisateur.pk:
            raise PermissionDeniedError("L'hôte ne peut pas accepter sa propre invitation.")
        if match.statut != Match.Statut.EN_ATTENTE:
            raise MatchAlreadyStartedError("La partie a déjà commencé.")
        if match.joueur_invite_id not in (utilisateur.pk, None):
            raise PermissionDeniedError("Cette partie ne vous est pas destinée.")
        if not hasattr(utilisateur, "portefeuille"):
            raise ValidationError("Portefeuille introuvable.")

        if not match.joueur_invite_id:
            match.joueur_invite = utilisateur
            match.save(update_fields=["joueur_invite"])

        if match.mise > 0:
            proposition = _valider_mise(match.mise, utilisateur.portefeuille)
            match.mise_proposee_invite = proposition
            match.save(update_fields=["mise_proposee_invite"])
            wallet_services.bloquer_mise(
                utilisateur.portefeuille,
                proposition,
                reference=_mise_reference(match, utilisateur),
                metadata={"match": match.pk, "role": "invite", "type_jeu": "course_lapin"},
                idempotency_key=f"reserve:{match.pk}:{utilisateur.pk}",
            )
            eff = match.mise_effective
            wallet_services.engager_mise(
                match.joueur_hote.portefeuille,
                eff,
                reference=f"engage-match-{match.pk}-{match.joueur_hote.pk}",
                metadata={"match": match.pk},
            )
            wallet_services.engager_mise(
                utilisateur.portefeuille,
                eff,
                reference=f"engage-match-{match.pk}-{utilisateur.pk}",
                metadata={"match": match.pk},
            )

        match.commence_le = timezone.now()
        match.save(update_fields=["commence_le"])
        Participation.objects.get_or_create(match=match, utilisateur=match.joueur_hote, defaults={"score_final": 0})
        Participation.objects.get_or_create(match=match, utilisateur=utilisateur, defaults={"score_final": 0})

    envoyer_notification(
        match.joueur_hote,
        Notification.Type.DEFI_ACCEPTE,
        "Tous les joueurs sont prêts",
        f"{utilisateur.pseudo} a accepté l'invitation. Tous les joueurs sont prêts. Lancez le compte à rebours de 5 secondes.",
        reference_id=match.pk,
        expediteur=utilisateur,
    )
    _broadcast(
        match.pk,
        {
            "type": "rabbit.invite_accepted",
            "match_id": match.pk,
            "invite_id": utilisateur.pk,
            "invite_pseudo": utilisateur.pseudo,
            "joueurs": [match.joueur_hote.pseudo, utilisateur.pseudo],
            "score_cible": match.score_cible,
            "type_jeu": match.type_jeu,
            "statut": match.statut,
        },
    )
    return match


def refuser_invitation_course_lapin(utilisateur, match_id: int) -> Match:
    with transaction.atomic():
        try:
            match = Match.objects.select_for_update().select_related("theme", "joueur_hote", "joueur_invite").get(pk=match_id)
        except Match.DoesNotExist:
            raise MatchNotFoundError()

        if match.type_jeu != Match.TypeJeu.COURSE_LAPIN:
            raise ValidationError("Cette invitation n'est pas une partie Course lapin.")
        if match.statut not in (Match.Statut.EN_ATTENTE,):
            raise MatchAlreadyStartedError("La partie a déjà commencé.")

        est_hote = match.joueur_hote_id == utilisateur.pk
        est_invite = match.joueur_invite_id == utilisateur.pk
        if not est_hote and not est_invite:
            raise PermissionDeniedError("Vous n'êtes pas concerné par cette invitation.")
        if not match.joueur_invite_id:
            return match

        ancien_invite = match.joueur_invite
        match.joueur_invite = None
        match.commence_le = None
        if match.mise_proposee_invite:
            match.mise_proposee_invite = None
        match.save(update_fields=["joueur_invite", "commence_le", "mise_proposee_invite"])
        Participation.objects.filter(match=match, utilisateur=ancien_invite).delete()

        # Si l'invité avait déjà réservé sa mise (accepté puis retiré avant lancement),
        # on libère la somme réservée — jamais une déduction.
        if match.mise > 0 and hasattr(ancien_invite, "portefeuille"):
            wallet_services.liberer_mise(
                ancien_invite.portefeuille,
                match.mise,
                type_=wallet_services.LedgerEntry.Type.REMBOURSEMENT,
                reference=f"refus-{match.pk}-{ancien_invite.pk}",
                metadata={"match": match.pk, "motif": "invitation_refusee_ou_retiree"},
                idempotency_key=f"refus:{match.pk}:{ancien_invite.pk}",
            )

    destinataire = match.joueur_hote if est_invite else ancien_invite
    if destinataire:
        envoyer_notification(
            destinataire,
            Notification.Type.SYSTEME,
            "Invitation Course lapin refusée",
            f"{utilisateur.pseudo} a refusé l'invitation Course lapin.",
            reference_id=match.pk,
            expediteur=utilisateur,
        )
    _broadcast(
        match.pk,
        {
            "type": "rabbit.invite_refused",
            "match_id": match.pk,
            "by_id": utilisateur.pk,
            "by_pseudo": utilisateur.pseudo,
            "statut": match.statut,
        },
    )
    return match


def lancer_course_lapin(utilisateur, match_id: int) -> Match:
    try:
        match = Match.objects.select_related("theme", "joueur_hote", "joueur_invite").get(pk=match_id)
    except Match.DoesNotExist:
        raise MatchNotFoundError()

    if match.type_jeu != Match.TypeJeu.COURSE_LAPIN:
        raise ValidationError("Cette partie n'est pas une Course lapin.")
    if match.joueur_hote_id != utilisateur.pk:
        raise PermissionDeniedError("Vous n'êtes pas l'hôte de cette partie.")
    if not match.joueur_invite:
        raise ValidationError("Un invité doit accepter l'invitation avant de lancer la partie.")
    if not match.commence_le:
        raise ValidationError("Tous les joueurs ne sont pas encore prêts.")

    match.statut = Match.Statut.EN_COURS
    match.save(update_fields=["statut"])

    _broadcast(
        match.pk,
        {
            "type": "rabbit.countdown",
            "match_id": match.pk,
            "seconds": 5,
            "joueurs": [match.joueur_hote.pseudo, match.joueur_invite.pseudo],
            "score_cible": match.score_cible,
            "type_jeu": match.type_jeu,
            "statut": match.statut,
        },
    )
    return match


def defier_joueur(utilisateur, invite_id: int, score_cible: int = 3) -> dict:
    if invite_id == utilisateur.pk:
        raise ValidationError("Vous ne pouvez pas vous défier vous-même.")
    if score_cible < 1:
        raise ValidationError("Le score cible doit être au moins de 1.")

    User = get_user_model()
    try:
        invite = User.objects.get(pk=invite_id)
    except User.DoesNotExist:
        raise NotFoundError("Joueur introuvable.")

    challenge_id = uuid.uuid4().hex
    challenge = {
        "id": challenge_id,
        "from_id": utilisateur.pk,
        "from_pseudo": utilisateur.pseudo,
        "to_id": invite.pk,
        "to_pseudo": invite.pseudo,
        "score_cible": int(score_cible),
        "created": timezone.now().isoformat(),
    }
    RPS_CHALLENGES[challenge_id] = challenge
    envoyer_notification(
        invite,
        Notification.Type.DEFI_RECU,
        "Nouveau défi",
        f"{utilisateur.pseudo} vous a défié en pierre, papier, ciseaux. Score cible : {score_cible}.",
        reference_id=0,
        expediteur=utilisateur,
    )
    return challenge


def accepter_defi(utilisateur, challenge_id: str) -> dict:
    challenge = RPS_CHALLENGES.get(challenge_id)
    if not challenge:
        raise NotFoundError("Défi introuvable.")
    if challenge["to_id"] != utilisateur.pk:
        raise PermissionDeniedError("Vous n'êtes pas le destinataire de ce défi.")

    match_id = f"rps-{uuid.uuid4().hex[:8]}"
    score_cible = int(challenge.get("score_cible", 3))
    match = {
        "id": match_id,
        "joueur_hote_id": challenge["from_id"],
        "joueur_hote_pseudo": challenge["from_pseudo"],
        "joueur_invite_id": challenge["to_id"],
        "joueur_invite_pseudo": challenge["to_pseudo"],
        "score_hote": 0,
        "score_invite": 0,
        "score_cible": score_cible,
        "round": 1,
        "statut": "en_cours",
        "moves": {},
        "winner_id": None,
    }
    RPS_MATCHES[match_id] = match
    del RPS_CHALLENGES[challenge_id]

    envoyeur = get_user_model().objects.filter(pk=challenge["from_id"]).first()
    if envoyeur:
        envoyer_notification(
            envoyeur,
            Notification.Type.DEFI_ACCEPTE,
            "Défi accepté",
            f"{utilisateur.pseudo} a accepté votre défi en pierre, papier, ciseaux.",
            reference_id=0,
            expediteur=utilisateur,
        )
    _broadcast_rps_match(match_id, match)
    return match


def demarrer_revanche(match_id: str) -> dict:
    """Démarre une revanche pour un match RPS terminé."""
    match = RPS_MATCHES.get(match_id)
    if not match:
        raise NotFoundError("Match introuvable.")
    if match.get("statut") != "termine":
        raise ValidationError("Seuls les matchs terminés peuvent avoir une revanche.")

    # Créer un nouveau match avec les mêmes joueurs
    new_match_id = f"rps-{uuid.uuid4().hex[:8]}"
    new_match = {
        "id": new_match_id,
        "joueur_hote_id": match["joueur_hote_id"],
        "joueur_hote_pseudo": match["joueur_hote_pseudo"],
        "joueur_invite_id": match["joueur_invite_id"],
        "joueur_invite_pseudo": match["joueur_invite_pseudo"],
        "score_hote": 0,
        "score_invite": 0,
        "score_cible": match["score_cible"],
        "round": 1,
        "statut": "en_cours",
        "moves": {},
        "winner_id": None,
    }
    RPS_MATCHES[new_match_id] = new_match
    _broadcast_rps_match(new_match_id, new_match)
    return new_match


def supprimer_match_rps(utilisateur, match_id: str) -> bool:
    match = RPS_MATCHES.get(match_id)
    if not match:
        raise NotFoundError("Partie Rock Paper Scissors introuvable.")
    if match["joueur_hote_id"] != utilisateur.pk:
        raise PermissionDeniedError("Vous n'êtes pas l'hôte de cette partie.")

    del RPS_MATCHES[match_id]
    return True


def jouer_coup(utilisateur, match_id: str, coup: str) -> dict:
    match = RPS_MATCHES.get(match_id)
    if not match:
        raise NotFoundError("Partie Rock Paper Scissors introuvable.")

    coup = coup.lower().strip()
    if coup not in {"pierre", "papier", "ciseaux"}:
        raise ValidationError("Coup invalide. Choisissez pierre, papier ou ciseaux.")

    if utilisateur.pk not in (match["joueur_hote_id"], match["joueur_invite_id"]):
        raise PermissionDeniedError("Vous ne participez pas à cette partie.")

    if match["statut"] == "termine":
        RPS_MATCHES[match_id] = match
        _broadcast_rps_match(match_id, match)
        return match

    current_player = str(utilisateur.pk)
    if current_player in match["moves"]:
        RPS_MATCHES[match_id] = match
        _broadcast_rps_match(match_id, match)
        return match

    match["moves"][current_player] = coup
    RPS_MATCHES[match_id] = match

    if len(match["moves"]) < 2:
        _broadcast_rps_match(match_id, match)
        return match

    player_ids = list(match["moves"].keys())
    first_player, second_player = player_ids[:2]
    first_coup = match["moves"][first_player]
    second_coup = match["moves"][second_player]
    winner = None
    if first_coup != second_coup:
        beats = {"pierre": "ciseaux", "ciseaux": "papier", "papier": "pierre"}
        winner = first_player if beats[first_coup] == second_coup else second_player

    match["moves"] = {}
    match["round"] += 1

    if winner is None:
        match["resultat_manche"] = "Égalité — personne ne marque et la manche passe directement à la suivante."
        RPS_MATCHES[match_id] = match
        return match

    winner_id = int(winner)
    if winner_id == match["joueur_hote_id"]:
        match["score_hote"] += 1
        message = f"{match['joueur_hote_pseudo']} gagne la manche : {first_coup} bat {second_coup}."
    else:
        match["score_invite"] += 1
        message = f"{match['joueur_invite_pseudo']} gagne la manche : {second_coup} bat {first_coup}."

    if match["score_hote"] >= match["score_cible"] or match["score_invite"] >= match["score_cible"]:
        match["statut"] = "termine"
        match["winner_id"] = match["joueur_hote_id"] if match["score_hote"] >= match["score_cible"] else match["joueur_invite_id"]
        match["resultat_manche"] = (
            f"Victoire finale ! {match['joueur_hote_pseudo']} remporte la partie."
            if match["score_hote"] >= match["score_cible"]
            else f"Victoire finale ! {match['joueur_invite_pseudo']} remporte la partie."
        )
    else:
        match["resultat_manche"] = message

    RPS_MATCHES[match_id] = match
    return match


# ==================== PENALTY KICK GAME ====================

def _broadcast_penalty_match(match_id: str, match: dict):
    try:
        channel_layer = get_channel_layer()
        async_to_sync(channel_layer.group_send)(
            f"penalty_{match_id}",
            {
                "type": "penalty.event",
                "data": {
                    "type": "penalty.update",
                    "match": match,
                },
            },
        )
    except Exception as e:
        logger.error(f"Erreur diffusion penalty match {match_id}: {e}")


def defier_joueur_penalty(utilisateur, invite_id: str, score_cible: int = 5) -> dict:
    """Crée un défi de tir au but."""
    if utilisateur.pk == int(invite_id):
        raise ValidationError("Vous ne pouvez pas vous défier vous-même.")
    
    invite = get_user_model().objects.filter(pk=invite_id).first()
    if not invite:
        raise NotFoundError("Utilisateur invité introuvable.")
    
    challenge_id = f"penalty-{uuid.uuid4().hex[:8]}"
    challenge = {
        "id": challenge_id,
        "hote_id": str(utilisateur.pk),
        "hote_pseudo": utilisateur.pseudo,
        "invite_id": invite_id,
        "invite_pseudo": invite.pseudo,
        "score_cible": score_cible,
        "statut": "en_attente",
        "round": 1,
        "score_hote": 0,
        "score_invite": 0,
        "shots": {},
        "resultat_manche": None,
        "winner_id": None,
    }
    PENALTY_CHALLENGES[challenge_id] = challenge
    
    envoyer_notification(
        invite,
        Notification.Type.DEFI_RECU,
        "Défi Tir au but",
        f"{utilisateur.pseudo} vous défie à un duel de tir au but ! Score cible : {score_cible}.",
        reference_id=0,
        expediteur=utilisateur,
    )
    return challenge


def accepter_defi_penalty(utilisateur, challenge_id: str) -> dict:
    """Accepte un défi de tir au but et crée le match."""
    challenge = PENALTY_CHALLENGES.get(challenge_id)
    if not challenge:
        raise NotFoundError("Défi introuvable.")
    
    if str(utilisateur.pk) != challenge["invite_id"]:
        raise PermissionDeniedError("Ce défi ne vous est pas destiné.")
    
    if challenge["statut"] != "en_attente":
        raise ValidationError("Ce défi a déjà été accepté.")
    
    match_id = f"penalty-{uuid.uuid4().hex[:8]}"
    match = {
        "id": match_id,
        "joueur_hote_id": challenge["hote_id"],
        "joueur_hote_pseudo": challenge["hote_pseudo"],
        "joueur_invite_id": challenge["invite_id"],
        "joueur_invite_pseudo": challenge["invite_pseudo"],
        "score_cible": challenge["score_cible"],
        "round": 1,
        "score_hote": 0,
        "score_invite": 0,
        "statut": "en_cours",
        "shots": {},
        "resultat_manche": None,
        "winner_id": None,
    }
    PENALTY_MATCHES[match_id] = match
    del PENALTY_CHALLENGES[challenge_id]
    
    _broadcast_penalty_match(match_id, match)
    return match


def jouer_tir_penalty(utilisateur, match_id: str, direction: str) -> dict:
    """Joue un tir au but."""
    match = PENALTY_MATCHES.get(match_id)
    if not match:
        raise NotFoundError("Match tir au but introuvable.")
    
    direction = direction.lower().strip()
    if direction not in {"gauche", "centre", "droite"}:
        raise ValidationError("Direction invalide. Choisissez gauche, centre ou droite.")
    
    if str(utilisateur.pk) not in (match["joueur_hote_id"], match["joueur_invite_id"]):
        raise PermissionDeniedError("Vous ne participez pas à ce match.")
    
    if match["statut"] == "termine":
        _broadcast_penalty_match(match_id, match)
        return match
    
    player_id = str(utilisateur.pk)
    if player_id in match["shots"]:
        _broadcast_penalty_match(match_id, match)
        return match
    
    # Simulation du tir: 70% de chance de réussir si direction aléatoire du gardien ne correspond pas
    import random
    gardien_direction = random.choice(["gauche", "centre", "droite"])
    but_marque = direction != gardien_direction
    
    match["shots"][player_id] = {
        "direction": direction,
        "but": but_marque,
        "gardien_direction": gardien_direction,
    }
    
    if but_marque:
        if player_id == match["joueur_hote_id"]:
            match["score_hote"] += 1
            match["resultat_manche"] = f"{match['joueur_hote_pseudo']} marque ! Tir {direction}, gardien {gardien_direction}."
        else:
            match["score_invite"] += 1
            match["resultat_manche"] = f"{match['joueur_invite_pseudo']} marque ! Tir {direction}, gardien {gardien_direction}."
    else:
        match["resultat_manche"] = f"{utilisateur.pseudo} rate ! Tir {direction}, gardien {gardien_direction}."
    
    # Vérifier si le match est terminé
    if match["score_hote"] >= match["score_cible"] or match["score_invite"] >= match["score_cible"]:
        match["statut"] = "termine"
        match["winner_id"] = match["joueur_hote_id"] if match["score_hote"] >= match["score_cible"] else match["joueur_invite_id"]
        winner_pseudo = match["joueur_hote_pseudo"] if match["score_hote"] >= match["score_cible"] else match["joueur_invite_pseudo"]
        match["resultat_manche"] = f"Victoire finale ! {winner_pseudo} remporte le duel de tir au but !"
    
    PENALTY_MATCHES[match_id] = match
    _broadcast_penalty_match(match_id, match)
    return match


def mes_defis_penalty(utilisateur) -> list[dict]:
    """Retourne les défis de tir au but en attente pour l'utilisateur."""
    challenges = []
    for challenge in PENALTY_CHALLENGES.values():
        if str(utilisateur.pk) == str(challenge.get("invite_id")):
            challenges.append(challenge)
    return challenges


def mes_matchs_penalty(utilisateur) -> list:
    """Retourne les matchs de tir au but de l'utilisateur."""
    matches = []
    for match in PENALTY_MATCHES.values():
        if str(utilisateur.pk) in (match["joueur_hote_id"], match["joueur_invite_id"]):
            matches.append(match)
    return matches


def parties_penalty_disponibles() -> list:
    """Retourne les matchs de tir au but disponibles pour les spectateurs."""
    return [match for match in PENALTY_MATCHES.values() if match["statut"] == "en_cours"]


def demarrer_revanche_penalty(match_id: str) -> dict:
    """Démarre une revanche pour un match de tir au but terminé."""
    match = PENALTY_MATCHES.get(match_id)
    if not match:
        raise NotFoundError("Match introuvable.")
    if match.get("statut") != "termine":
        raise ValidationError("Seuls les matchs terminés peuvent avoir une revanche.")
    
    new_match_id = f"penalty-{uuid.uuid4().hex[:8]}"
    new_match = {
        "id": new_match_id,
        "joueur_hote_id": match["joueur_hote_id"],
        "joueur_hote_pseudo": match["joueur_hote_pseudo"],
        "joueur_invite_id": match["joueur_invite_id"],
        "joueur_invite_pseudo": match["joueur_invite_pseudo"],
        "score_hote": 0,
        "score_invite": 0,
        "score_cible": match["score_cible"],
        "round": 1,
        "statut": "en_cours",
        "shots": {},
        "resultat_manche": None,
        "winner_id": None,
    }
    PENALTY_MATCHES[new_match_id] = new_match
    _broadcast_penalty_match(new_match_id, new_match)
    return new_match


def supprimer_match_penalty(utilisateur, match_id: str) -> bool:
    match = PENALTY_MATCHES.get(match_id)
    if not match:
        raise NotFoundError("Match tir au but introuvable.")
    if match["joueur_hote_id"] != str(utilisateur.pk):
        raise PermissionDeniedError("Vous n'êtes pas l'hôte de ce match.")
    
    del PENALTY_MATCHES[match_id]
    return True