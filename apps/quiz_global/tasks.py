from celery import shared_task


@shared_task(queue="matches")
def quiz_global_tick(game_id: int):
    from apps.quiz_global.services import tick

    return tick(game_id)
