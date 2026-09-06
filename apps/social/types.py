import strawberry
import strawberry_django

from apps.social import models
from apps.users.types import UtilisateurType


@strawberry_django.type(models.Publication)
class PublicationType:
    id: strawberry.auto
    texte: strawberry.auto
    image: strawberry.auto
    lien_type: strawberry.auto
    reference_id: strawberry.auto
    auteur: UtilisateurType
    cree_le: strawberry.auto

    @strawberry.field
    def nombre_reactions(self) -> int:
        return self.nombre_reactions

    @strawberry.field
    def nombre_commentaires(self) -> int:
        return self.nombre_commentaires

    @strawberry.field
    def jaime_par_moi(self, info: strawberry.Info) -> bool:
        user = info.context.request.user
        if user.is_anonymous:
            return False
        return self.reactions.filter(auteur=user).exists()


@strawberry_django.type(models.Commentaire)
class CommentaireType:
    id: strawberry.auto
    texte: strawberry.auto
    auteur: UtilisateurType
    cree_le: strawberry.auto


@strawberry_django.type(models.Notification)
class NotificationType:
    id: strawberry.auto
    type: strawberry.auto
    titre: strawberry.auto
    message: strawberry.auto
    lu: strawberry.auto
    reference_id: strawberry.auto
    destinataire: UtilisateurType
    expediteur: UtilisateurType | None
    cree_le: strawberry.auto


@strawberry_django.type(models.DemandeAmi)
class DemandeAmiType:
    id: strawberry.auto
    statut: strawberry.auto
    demandeur: UtilisateurType
    receveur: UtilisateurType
    cree_le: strawberry.auto