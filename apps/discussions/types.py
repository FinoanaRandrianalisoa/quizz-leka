import strawberry
import strawberry_django

from apps.discussions import models
from apps.users.types import UtilisateurType


@strawberry_django.type(models.Ville)
class VilleType:
    id: strawberry.auto
    nom: strawberry.auto
    slug: strawberry.auto

    @strawberry.field
    def nombre_messages(self) -> int:
        return self.messages.count()


@strawberry_django.type(models.Message)
class MessageType:
    id: strawberry.auto
    contenu: strawberry.auto
    utilisateur: UtilisateurType
    cree_le: strawberry.auto


@strawberry_django.type(models.MessageAmi)
class MessageAmiType:
    id: strawberry.auto
    contenu: strawberry.auto
    expediteur: UtilisateurType
    destinataire: UtilisateurType
    lu: strawberry.auto
    cree_le: strawberry.auto


@strawberry.type
class ConversationType:
    """Discussion unifiée (privée avec un ami ou groupe de ville)."""

    type_: str = strawberry.field(name="type")
    identifiant: str
    adversaire: UtilisateurType | None = None
    ville: VilleType | None = None
    dernier_message: str = ""
    dernier_expediteur: UtilisateurType | None = None
    dernier_message_horodatage: str = ""
    non_lus: int = 0