from common.graphql.errors import DomainError, RateLimitedError


def domain_to_extensions(exc: DomainError) -> dict:
    """Convertit une exception métier en `extensions` GraphQL normalisées."""
    extensions = {
        "code": exc.code,
    }
    if isinstance(exc, RateLimitedError) and exc.retry_after is not None:
        extensions["retry_after"] = exc.retry_after
    return extensions
