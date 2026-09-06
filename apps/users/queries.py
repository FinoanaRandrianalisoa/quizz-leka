import re
import secrets

from django.db.models import Count, Q, Sum

import strawberry
from strawberry.types import Info

from apps.matches.models import Match
from apps.themes.models import Question
from apps.users.models import Utilisateur
from apps.users.types import ClassementEntryType, ProfilType, StatsPlateformeType, UtilisateurType
from apps.wallet.models import LedgerEntry
from common.graphql.permissions import get_current_user


def resolve_moi(info: Info) -> UtilisateurType:
    return get_current_user(info)


def resolve_profil(info: Info) -> ProfilType:
    user = get_current_user(info)
    stats = user.stats
    parties = stats["parties"]
    victoires = stats["victoires"]
    gains = (
        LedgerEntry.objects.filter(
            portefeuille__utilisateur=user,
            type=LedgerEntry.Type.GAIN,
            statut=LedgerEntry.Statut.SUCCES,
        ).aggregate(s=Sum("montant"))["s"]
        or 0
    )
    return ProfilType(
        utilisateur=user,
        parties_jouees=parties,
        victoires=victoires,
        defaites=max(0, parties - victoires),
        taux_reussite=round(victoires / parties, 2) if parties else 0.0,
        cumul_gains=str(gains),
    )


def resolve_classement(info: Info, limit: int = 20) -> list[ClassementEntryType]:
    qs = Utilisateur.objects.annotate(
        nb_parties=Count("participations"),
        nb_victoires=Count("participations", filter=Q(participations__vainqueur=True)),
    ).order_by("-nb_victoires", "-nb_parties", "pseudo")[: min(limit, 100)]
    entries = []
    for i, user in enumerate(qs, start=1):
        parties = user.nb_parties
        victoires = user.nb_victoires
        entries.append(
            ClassementEntryType(
                rang=i,
                utilisateur=user,
                parties=parties,
                victoires=victoires,
                defaites=max(0, parties - victoires),
                taux_reussite=round((victoires / parties) * 100) if parties else 0.0,
            )
        )
    return entries


def resolve_stats_plateforme(info: Info) -> StatsPlateformeType:
    return StatsPlateformeType(
        joueurs=Utilisateur.objects.count(),
        questions=Question.objects.filter(validee=True).count(),
        joueurs_en_ligne=Utilisateur.objects.filter(en_ligne=True).count(),
        parties_en_cours=Match.objects.filter(statut=Match.Statut.EN_COURS).count(),
    )


def resolve_utilisateurs(info: Info, recherche: str | None = None, limit: int = 50) -> list[UtilisateurType]:
    qs = Utilisateur.objects.all().order_by("-date_joined")
    if recherche:
        qs = qs.filter(Q(pseudo__icontains=recherche) | Q(email__icontains=recherche))
    return list(qs[: min(limit, 100)])


@strawberry.type
class PseudoInfoType:
    disponible: bool
    suggestion: str


def _base_pseudo(pseudo: str) -> str:
    return re.sub(r"\d+$", "", pseudo.strip().lower())[:50]


def resolve_pseudo_info(info: Info, pseudo: str) -> PseudoInfoType:
    base = _base_pseudo(pseudo)
    if not base:
        return PseudoInfoType(disponible=False, suggestion="")
    if not Utilisateur.objects.filter(pseudo__iexact=base).exists():
        return PseudoInfoType(disponible=True, suggestion=base)
    for i in range(1, 10_000):
        candidat = f"{base}{i}"
        if not Utilisateur.objects.filter(pseudo__iexact=candidat).exists():
            return PseudoInfoType(disponible=False, suggestion=candidat)
    return PseudoInfoType(disponible=False, suggestion=f"{base}{secrets.randbelow(900_000) + 100_000}")


@strawberry.type
class UsersQuery:
    moi: UtilisateurType = strawberry.field(resolver=resolve_moi)
    profil: ProfilType = strawberry.field(resolver=resolve_profil)
    classement: list[ClassementEntryType] = strawberry.field(resolver=resolve_classement)
    stats_plateforme: StatsPlateformeType = strawberry.field(resolver=resolve_stats_plateforme)
    utilisateurs: list[UtilisateurType] = strawberry.field(resolver=resolve_utilisateurs)
    pseudo_info: PseudoInfoType = strawberry.field(resolver=resolve_pseudo_info)
