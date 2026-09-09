from celery import shared_task


@shared_task(queue="matches")
def quiz_global_tick(game_id: int):
    from apps.quiz_global.services import tick

    return tick(game_id)


@shared_task(queue="matches")
def quiz_global_cleanup_waiting_periodic():
    """Annule périodiquement les salons Quizz Global restés à l'état WAITING trop longtemps."""
    from apps.quiz_global.services import expirer_parties_en_attente

    return expirer_parties_en_attente()
