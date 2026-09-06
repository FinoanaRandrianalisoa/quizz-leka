import strawberry
from django.db.models import Q
from strawberry.types import Info

from apps.social import models
from apps.social.models import Publication, DemandeAmi, Commentaire, Notification
from apps.social.types import PublicationType, DemandeAmiType, CommentaireType, NotificationType
from apps.users.types import UtilisateurType
from common.graphql.permissions import get_current_user


def resolve_fil_actualite(info: Info, limit: int = 20, offset: int = 0) -> list[PublicationType]:
    return list(
        Publication.objects.filter(statut=Publication.Statut.PUBLIE)
        .select_related("auteur")
        .prefetch_related("reactions", "commentaires")
        .order_by("-cree_le")[offset : offset + min(limit, 50)]
    )


def resolve_mes_amis(info: Info) -> list[UtilisateurType]:
    user = get_current_user(info)
    demandes = DemandeAmi.objects.filter(
        statut=DemandeAmi.Statut.ACCEPTEE,
    ).filter(Q(demandeur=user) | Q(receveur=user))
    amis = set()
    for d in demandes:
        amis.add(d.receveur if d.demandeur_id == user.pk else d.demandeur)
    return list(amis)


def resolve_demandes_amis_recues(info: Info, limit: int = 20) -> list[DemandeAmiType]:
    return list(
        DemandeAmi.objects.filter(receveur=get_current_user(info), statut=DemandeAmi.Statut.EN_ATTENTE)
        .select_related("demandeur")
        .order_by("-cree_le")[: min(limit, 50)]
    )


def resolve_demandes_amis_envoyees(info: Info, limit: int = 20) -> list[DemandeAmiType]:
    return list(
        DemandeAmi.objects.filter(demandeur=get_current_user(info), statut=DemandeAmi.Statut.EN_ATTENTE)
        .select_related("receveur")
        .order_by("-cree_le")[: min(limit, 50)]
    )


def resolve_commentaires(info: Info, publication_id: int, limit: int = 30) -> list[CommentaireType]:
    return list(
        Commentaire.objects.filter(publication_id=publication_id)
        .select_related("auteur")
        .order_by("cree_le")[: min(limit, 50)]
    )


def resolve_mes_notifications(info: Info, limit: int = 20) -> list[NotificationType]:
    return list(
        Notification.objects.filter(destinataire=get_current_user(info))
        .order_by("-cree_le")[: min(limit, 50)]
    )


@strawberry.type
class SocialQuery:
    fil_actualite: list[PublicationType] = strawberry.field(resolver=resolve_fil_actualite)
    mes_amis: list[UtilisateurType] = strawberry.field(resolver=resolve_mes_amis)
    demandes_amis_recues: list[DemandeAmiType] = strawberry.field(resolver=resolve_demandes_amis_recues)
    demandes_amis_envoyees: list[DemandeAmiType] = strawberry.field(resolver=resolve_demandes_amis_envoyees)
    mes_notifications: list[NotificationType] = strawberry.field(resolver=resolve_mes_notifications)
    commentaires: list[CommentaireType] = strawberry.field(resolver=resolve_commentaires)