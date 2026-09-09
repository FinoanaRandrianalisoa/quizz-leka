from celery import shared_task


@shared_task(queue="matches")
def quiz_global_tick(game_id: int):
    from apps.quiz_global.services import tick

    return tick(game_id)


@shared_task(queue="matches")
def quiz_global_cleanup_waiting_periodic():
    """Passe périodiquement les salons Quizz Global restés WAITING trop longtemps à EXPIRED."""
    from apps.quiz_global.services import expirer_parties_en_attente

    return expirer_parties_en_attente()


@shared_task(queue="matches")
def quiz_global_cleanup_abandoned_periodic():
    """Passe à ABANDONED les parties restées bloquées sans progression de phase."""
    from apps.quiz_global.services import abandonner_parties_bloquees

    return abandonner_parties_bloquees()
