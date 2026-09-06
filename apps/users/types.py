import strawberry
import strawberry_django
from strawberry.types import Info

from apps.users import models


@strawberry_django.type(models.Utilisateur)
class UtilisateurType:
    id: strawberry.auto
    pseudo: strawberry.auto
    email: strawberry.auto
    telephone: strawberry.auto
    date_naissance: strawberry.auto
    first_name: strawberry.auto
    last_name: strawberry.auto
    code_parrain: strawberry.auto
    ville_origine: strawberry.auto
    role: strawberry.auto
    en_ligne: strawberry.auto
    date_joined: strawberry.auto

    @strawberry.field
    def photo_profil(self, info: Info) -> str | None:
        image = getattr(self, "photo_profil", None)
        if not image:
            return None
        url = image.url if getattr(image, "url", None) else str(image)
        request = getattr(info.context, "request", None)
        if request is not None:
            return request.build_absolute_uri(url)
        return url

    @strawberry.field
    def photo_couverture(self, info: Info) -> str | None:
        image = getattr(self, "photo_couverture", None)
        if not image:
            return None
        url = image.url if getattr(image, "url", None) else str(image)
        request = getattr(info.context, "request", None)
        if request is not None:
            return request.build_absolute_uri(url)
        return url


@strawberry.type
class ProfilType:
    utilisateur: UtilisateurType
    parties_jouees: int
    victoires: int
    defaites: int
    taux_reussite: float
    cumul_gains: str


@strawberry.type
class ClassementEntryType:
    rang: int
    utilisateur: UtilisateurType
    parties: int
    victoires: int
    defaites: int
    taux_reussite: float


@strawberry.type
class StatsPlateformeType:
    joueurs: int
    questions: int
    joueurs_en_ligne: int
    parties_en_cours: int
