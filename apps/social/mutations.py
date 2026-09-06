import strawberry
from strawberry.types import Info

from apps.social import services
from apps.social.types import PublicationType
from common.graphql.permissions import get_current_user


@strawberry.type
class SocialMutation:
    @strawberry.mutation
    def publier(info: Info, texte: str) -> PublicationType:
        return services.publier(get_current_user(info), texte)

    @strawberry.mutation
    def supprimer_publication(info: Info, publication_id: int) -> bool:
        return services.supprimer_publication(get_current_user(info), publication_id)

    @strawberry.mutation
    def commenter(info: Info, publication_id: int, texte: str) -> bool:
        return services.commenter(get_current_user(info), publication_id, texte)

    @strawberry.mutation
    def aimer_publication(info: Info, publication_id: int) -> bool:
        return services.aimer(get_current_user(info), publication_id)

    @strawberry.mutation
    def envoyer_demande_ami(info: Info, pseudo: str) -> bool:
        return services.envoyer_demande_ami(get_current_user(info), pseudo)

    @strawberry.mutation
    def repondre_demande_ami(info: Info, demande_id: int, accepter: bool) -> bool:
        return services.repondre_demande_ami(get_current_user(info), demande_id, accepter)

    @strawberry.mutation
    def marquer_notification_lue(info: Info, notification_id: int) -> bool:
        utilisateur = get_current_user(info)
        notification = services.Notification.objects.filter(pk=notification_id, destinataire=utilisateur).first()
        if not notification:
            return False
        notification.lu = True
        notification.save(update_fields=["lu"])
        return True

    @strawberry.mutation
    def marquer_toutes_notifications_lues(info: Info) -> bool:
        utilisateur = get_current_user(info)
        services.Notification.objects.filter(destinataire=utilisateur, lu=False).update(lu=True)
        return True