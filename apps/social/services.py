from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from django.db.models import Q

from apps.social.models import DemandeAmi, Notification, Publication, Commentaire, Reaction
from common.graphql.errors import (
    CannotSelfFriendError,
    FriendRequestExistsError,
    NotFoundError,
    PermissionDeniedError,
)


def envoyer_notification(
    utilisateur, type_, titre: str, message: str, reference_id: int = 0, expediteur=None
) -> Notification:
    notification = Notification.objects.create(
        destinataire=utilisateur,
        expediteur=expediteur,
        type=type_,
        titre=titre,
        message=message,
        reference_id=reference_id,
    )
    try:
        channel_layer = get_channel_layer()
        async_to_sync(channel_layer.group_send)(
            f"notifications_{utilisateur.pk}",
            {
                "type": "notify",
                "data": {
                    "id": notification.id,
                    "type": notification.type,
                    "titre": notification.titre,
                    "message": notification.message,
                    "lu": notification.lu,
                    "reference_id": notification.reference_id,
                    "cree_le": notification.cree_le.isoformat(),
                },
            },
        )
    except Exception:
        pass
    return notification


def publier(utilisateur, texte: str) -> Publication:
    return Publication.objects.create(auteur=utilisateur, texte=texte)


def supprimer_publication(utilisateur, publication_id: int) -> bool:
    pub = Publication.objects.filter(pk=publication_id).first()
    if not pub:
        raise NotFoundError("Publication introuvable.")
    if pub.auteur != utilisateur and utilisateur.role != "ADMIN":
        raise PermissionDeniedError()
    pub.delete()
    return True


def commenter(utilisateur, publication_id: int, texte: str) -> bool:
    pub = Publication.objects.filter(pk=publication_id).first()
    if not pub:
        raise NotFoundError("Publication introuvable.")
    Commentaire.objects.create(publication=pub, auteur=utilisateur, texte=texte)
    return True


def aimer(utilisateur, publication_id: int) -> bool:
    pub = Publication.objects.filter(pk=publication_id).first()
    if not pub:
        raise NotFoundError("Publication introuvable.")
    reaction, cree = Reaction.objects.get_or_create(publication=pub, auteur=utilisateur)
    if not cree:
        reaction.delete()
    return cree


def envoyer_demande_ami(utilisateur, pseudo: str) -> bool:
    from apps.users.models import Utilisateur

    receveur = Utilisateur.objects.filter(pseudo__iexact=pseudo).first()
    if not receveur:
        raise NotFoundError("Utilisateur introuvable.")
    if receveur == utilisateur:
        raise CannotSelfFriendError()
    if DemandeAmi.objects.filter(
        Q(demandeur=utilisateur, receveur=receveur, statut=DemandeAmi.Statut.EN_ATTENTE)
        | Q(demandeur=receveur, receveur=utilisateur, statut=DemandeAmi.Statut.EN_ATTENTE),
    ).exists():
        raise FriendRequestExistsError()
    DemandeAmi.objects.create(demandeur=utilisateur, receveur=receveur)
    return True


def repondre_demande_ami(utilisateur, demande_id: int, accepter: bool) -> bool:
    demande = DemandeAmi.objects.filter(pk=demande_id).first()
    if not demande or demande.receveur != utilisateur:
        raise PermissionDeniedError()
    demande.statut = DemandeAmi.Statut.ACCEPTEE if accepter else DemandeAmi.Statut.REFUSEE
    demande.save(update_fields=["statut"])
    if accepter:
        envoyer_notification(
            demande.demandeur,
            Notification.Type.AMI_ACCEPTE,
            "Demande acceptée",
            f"{utilisateur.pseudo} a accepté votre demande d'ami.",
            demande.id,
            expediteur=utilisateur,
        )
    return True