from celery import shared_task


@shared_task(queue="matches")
def cloturer_retard_deconnexion(match_id: int):
    """Délai de grâce après déconnexion d'un joueur (RG-GAM abandon).

    MVP : tâche réservée — la logique complète (annulation avant le 1er tiers,
    forfait après) est à brancher sur l'événement de déconnexion du consumer.
    """
    return {"match_id": match_id, "statut": "a_traiter"}