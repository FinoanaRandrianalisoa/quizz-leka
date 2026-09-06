from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_exempt
from strawberry.django.views import GraphQLView
from strawberry.django.context import StrawberryDjangoContext

from apps.auth.middleware import get_user_from_request


@method_decorator(csrf_exempt, name="dispatch")
class JWTGraphQLView(GraphQLView):
    """Vue GraphQL qui injecte `request.user` authentifié par JWT (Authorization: Bearer)."""

    def get_context(self, request, response):
        request.user = get_user_from_request(request)
        return StrawberryDjangoContext(request=request, response=response)