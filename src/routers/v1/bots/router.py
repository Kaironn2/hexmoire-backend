from fastapi import APIRouter, HTTPException, status

from src.bots.base import BaseCrawler
from src.bots.registry import list_bots, get_bot
from src.routers.v1.bots.schemas import BotInfo, BotRunRequest, BotRunResponse
from src.tasks.steam import steam_crawl_achievements

bot_router = APIRouter(prefix='/bots', tags=['bots'])

_TASK_MAP: dict[str, object] = {
    'steam_achievements_crawler': steam_crawl_achievements,
}


def _resolve_bot_type(cls: type) -> str:
    if issubclass(cls, BaseCrawler):
        return 'crawler'
    return 'unknown'


@bot_router.get('', response_model=list[BotInfo])
async def list_registered_bots() -> list[BotInfo]:
    """Return every bot that has been registered via ``@register_bot``."""
    return [
        BotInfo(
            name=name,
            type=_resolve_bot_type(cls),
            module=cls.__module__,
        )
        for name, cls in list_bots().items()
    ]


@bot_router.post('/run', response_model=BotRunResponse)
async def run_bot(body: BotRunRequest) -> BotRunResponse:
    """Dispatch a registered bot as a background task.

    The bot must have a corresponding entry in the task map.
    Returns the TaskIQ task id so the caller can poll for results.
    """
    try:
        get_bot(body.name)
    except KeyError:
        available = list(list_bots().keys())
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f'Bot "{body.name}" not found. Available: {available}',
        )

    task = _TASK_MAP.get(body.name)
    if task is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f'Bot "{body.name}" has no runnable task configured.',
        )

    result = await task.kiq()  # type: ignore[union-attr]

    return BotRunResponse(
        name=body.name,
        task_id=result.task_id,
        status='queued',
    )
