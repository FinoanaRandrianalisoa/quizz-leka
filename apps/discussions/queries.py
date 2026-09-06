import strawberry
from django.db.models import Count, Q
from strawberry.types import Info

from apps.discussions.models import Ville, Message, MessageAmi
from apps.discussions.types import VilleType, MessageType, MessageAmiType, ConversationType
from apps.social.models import DemandeAmi
from apps.users.models import Utilisateur
from common.graphql.errors import NotFoundError, PermissionDeniedError
from common.graphql.permissions import get_current_user


def resolve_villes(info: Info) -> list[VilleType]:
    return list(Ville.objects.annotate(nb_messages=Count("messages")).order_by("nom"))


def resolve_messages_salon(info: Info, ville_slug: str, limit: int = 30, offset: int = 0) -> list[MessageType]:
    return list(
        Message.objects.filter(ville__slug=ville_slug)
        .select_related("utilisateur")
        .order_by("-cree_le")[offset : offset + min(limit, 60)]
    )


def resolve_messages_ami(info: Info, ami_id: int, limit: int = 30, offset: int = 0) -> list[MessageAmiType]:
    user = get_current_user(info)
    ami = Utilisateur.objects.filter(pk=ami_id).first()
    if not ami:
        raise NotFoundError("Utilisateur introuvable.")
    if not DemandeAmi.objects.filter(statut=DemandeAmi.Statut.ACCEPTEE).filter(Q(demandeur=user, receveur=ami) | Q(demandeur=ami, receveur=user)).exists():
        raise PermissionDeniedError("Vous devez être amis pour discuter en privé.")
    return list(
        MessageAmi.objects.filter(Q(expediteur=user, destinataire=ami) | Q(expediteur=ami, destinataire=user))
        .select_related("expediteur", "destinataire")
        .order_by("-cree_le")[offset : offset + min(limit, 100)]
    )


def resolve_envoyer_message_ville(info: Info, ville_slug: str, contenu: str) -> MessageType:
    user = get_current_user(info)
    ville = Ville.objects.filter(slug=ville_slug).first()
    if not ville:
        raise NotFoundError("Ville introuvable.")
    message = Message.objects.create(ville=ville, utilisateur=user, contenu=(contenu or "").strip())
    return message


def resolve_envoyer_message_ami(info: Info, ami_id: int, contenu: str) -> MessageAmiType:
    user = get_current_user(info)
    ami = Utilisateur.objects.filter(pk=ami_id).first()
    if not ami:
        raise NotFoundError("Utilisateur introuvable.")
    if not DemandeAmi.objects.filter(statut=DemandeAmi.Statut.ACCEPTEE).filter(Q(demandeur=user, receveur=ami) | Q(demandeur=ami, receveur=user)).exists():
        raise PermissionDeniedError("Vous devez être amis pour discuter en privé.")
    texte = (contenu or "").strip()
    if not texte:
        raise ValueError("Le message ne peut pas être vide.")
    message = MessageAmi.objects.create(expediteur=user, destinataire=ami, contenu=texte)
    return message


def resolve_nb_messages_non_lus(info: Info) -> int:
    user = get_current_user(info)
    return MessageAmi.objects.filter(destinataire=user, lu=False).count()


def resolve_marquer_messages_lus(info: Info, ami_id: int) -> bool:
    """Mark all messages from `ami_id` to current user as read."""
    user = get_current_user(info)
    ami = Utilisateur.objects.filter(pk=ami_id).first()
    if not ami:
        raise NotFoundError("Utilisateur introuvable.")
    # Ensure friendship
    if not DemandeAmi.objects.filter(statut=DemandeAmi.Statut.ACCEPTEE).filter(Q(demandeur=user, receveur=ami) | Q(demandeur=ami, receveur=user)).exists():
        raise PermissionDeniedError("Vous devez être amis pour marquer les messages lus.")
    MessageAmi.objects.filter(expediteur=ami, destinataire=user, lu=False).update(lu=True)
    return True


def resolve_discussions(info: Info) -> list[ConversationType]:
    """Liste unifiée des conversations (privées + groupes de ville), triée par activité."""
    me = get_current_user(info)
    amis = Utilisateur.objects.filter(
        Q(id__in=DemandeAmi.objects.filter(statut=DemandeAmi.Statut.ACCEPTEE, demandeur=me).values("receveur_id"))
        | Q(id__in=DemandeAmi.objects.filter(statut=DemandeAmi.Statut.ACCEPTEE, receveur=me).values("demandeur_id"))
    )
    conversations: list[ConversationType] = []
    for ami in amis:
        dernier = (
            MessageAmi.objects.filter(Q(expediteur=me, destinataire=ami) | Q(expediteur=ami, destinataire=me))
            .select_related("expediteur")
            .order_by("-cree_le")
            .first()
        )
        if not dernier:
            continue
        non_lus = MessageAmi.objects.filter(expediteur=ami, destinataire=me, lu=False).count()
        conversations.append(
            ConversationType(
                type_="ami",
                identifiant=f"ami:{ami.id}",
                adversaire=ami,
                dernier_message=dernier.contenu,
                dernier_expediteur=dernier.expediteur,
                dernier_message_horodatage=dernier.cree_le.isoformat() if dernier.cree_le else "",
                non_lus=non_lus,
            )
        )
    for ville in Ville.objects.all():
        dernier = (
            Message.objects.filter(ville=ville).select_related("utilisateur").order_by("-cree_le").first()
        )
        conversations.append(
            ConversationType(
                type_="groupe",
                identifiant=f"groupe:{ville.slug}",
                ville=ville,
                dernier_message=dernier.contenu if dernier else "",
                dernier_expediteur=dernier.utilisateur if dernier else None,
                dernier_message_horodatage=dernier.cree_le.isoformat() if dernier and dernier.cree_le else "",
                non_lus=0,
            )
        )
    conversations.sort(key=lambda c: c.dernier_message_horodatage, reverse=True)
    return conversations


@strawberry.type
class DiscussionsQuery:
    villes: list[VilleType] = strawberry.field(resolver=resolve_villes)
    messages_salon: list[MessageType] = strawberry.field(resolver=resolve_messages_salon)
    messages_ami: list[MessageAmiType] = strawberry.field(resolver=resolve_messages_ami)
    nb_messages_non_lus: int = strawberry.field(resolver=resolve_nb_messages_non_lus)
    discussions: list[ConversationType] = strawberry.field(resolver=resolve_discussions)


@strawberry.type
class DiscussionsMutation:
    envoyer_message_ville: MessageType = strawberry.field(resolver=resolve_envoyer_message_ville)
    envoyer_message_ami: MessageAmiType = strawberry.field(resolver=resolve_envoyer_message_ami)
    marquer_messages_lus: bool = strawberry.field(resolver=resolve_marquer_messages_lus)