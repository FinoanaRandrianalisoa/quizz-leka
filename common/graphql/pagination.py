import strawberry
from typing import Generic, TypeVar, Optional

T = TypeVar("T")


@strawberry.type
class PageInfo:
    has_next_page: bool
    has_previous_page: bool
    start_cursor: Optional[str] = None
    end_cursor: Optional[str] = None


@strawberry.type
class Connection(Generic[T]):
    total_count: int
    page_info: PageInfo
    items: list[T]


def paginate(items: list, total_count: int, has_more: bool) -> Connection:
    return Connection(
        total_count=total_count,
        page_info=PageInfo(has_next_page=has_more, has_previous_page=False),
        items=items,
    )
