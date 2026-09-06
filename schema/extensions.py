"""Extensions GraphQL : limites (depth/tokens/aliases) et normalisation des erreurs."""

from graphql.error import GraphQLError
from strawberry.extensions import SchemaExtension

from common.graphql.errors import DomainError
from common.graphql.errors_handler import domain_to_extensions


class ErrorNormalizer(SchemaExtension):
    """Normalise les erreurs GraphQL en `extensions.code` (registre commun).

    - Les erreurs métier (`DomainError`) sont exposées avec leur message + code.
    - Toute autre erreur devient `INTERNAL_ERROR` (message générique, aucune fuite).
    """

    def _process_result(self, result) -> None:
        errors = getattr(result, "errors", None)
        if not errors:
            return
        traités = []
        for error in errors:
            original = getattr(error, "original_error", None)
            if isinstance(original, DomainError):
                traités.append(
                    GraphQLError(
                        message=original.message,
                        nodes=error.nodes,
                        source=error.source,
                        positions=error.positions,
                        path=error.path,
                        original_error=original,
                        extensions=domain_to_extensions(original),
                    )
                )
                continue
            if original is None:
                # Erreur de parsing/validation GraphQL : laisser telle quelle.
                traités.append(error)
                continue
            # Exception non prévue : message générique, aucune fuite d'information.
            traités.append(
                GraphQLError(
                    message="Erreur interne, veuillez réessayer.",
                    nodes=error.nodes,
                    source=error.source,
                    positions=error.positions,
                    path=error.path,
                    original_error=None,
                    extensions={"code": "INTERNAL_ERROR"},
                )
            )
        result.errors = traités

    def on_operation(self):
        yield
        result = self.execution_context.result
        if hasattr(result, "errors") and getattr(result, "errors", None):
            self._process_result(result)
        elif initial := getattr(result, "initial_result", None):
            self._process_result(initial)