"""Assemblage du schéma GraphQL global (Query / Mutation racines)."""

import strawberry
from django.conf import settings
from strawberry.extensions import (
    DisableIntrospection,
    MaxAliasesLimiter,
    MaxTokensLimiter,
    QueryDepthLimiter,
)

from apps.auth.mutations import AuthMutation
from apps.betting.mutations import BettingMutation
from apps.betting.queries import BettingQuery
from apps.discussions.queries import DiscussionsMutation, DiscussionsQuery
from apps.matches.mutations import MatchesMutation
from apps.matches.queries import MatchesQuery
from apps.quiz_global.mutations import QuizGlobalMutation
from apps.quiz_global.queries import QuizGlobalQuery
from apps.social.mutations import SocialMutation
from apps.social.queries import SocialQuery
from apps.themes.mutations import ThemesMutation
from apps.themes.queries import ThemesQuery
from apps.users.mutations import UsersMutation
from apps.users.queries import UsersQuery
from apps.wallet.mutations import WalletMutation
from apps.wallet.queries import WalletQuery
from schema.extensions import ErrorNormalizer
from schema.views import JWTGraphQLView


@strawberry.type
class Query(UsersQuery, ThemesQuery, WalletQuery, MatchesQuery, BettingQuery, SocialQuery, DiscussionsQuery, QuizGlobalQuery):
    pass


@strawberry.type
class Mutation(
    AuthMutation,
    UsersMutation,
    WalletMutation,
    MatchesMutation,
    BettingMutation,
    SocialMutation,
    ThemesMutation,
    DiscussionsMutation,
    QuizGlobalMutation,
):
    pass


def _schema_extensions() -> list:
    extensions = [
        ErrorNormalizer,
        lambda: QueryDepthLimiter(max_depth=10),
        lambda: MaxTokensLimiter(max_token_count=5000),
        lambda: MaxAliasesLimiter(max_alias_count=150),
    ]
    if not getattr(settings, "GRAPHQL_INTROSPECTION_ENABLED", True):
        extensions.append(DisableIntrospection)
    return extensions


schema = strawberry.Schema(
    query=Query,
    mutation=Mutation,
    extensions=_schema_extensions(),
)

graphql_app = JWTGraphQLView.as_view(schema=schema)