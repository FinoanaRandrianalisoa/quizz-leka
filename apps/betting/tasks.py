from celery import shared_task


@shared_task(queue="payments")
def resoudre_paris_match(match_id: int):
    from apps.betting.services import resoudre_paris
    from apps.matches.models import Match

    match = Match.objects.select_related("vainqueur").filter(pk=match_id).first()
    if not match:
        return {"status": "match_introuvable"}
    resoudre_paris(match)
    return {"status": "ok", "match_id": match_id}