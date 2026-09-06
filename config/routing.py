from django.urls import path

from apps.discussions.consumers import CityChatConsumer, NotificationConsumer
from apps.matches.consumers import MatchConsumer, PartiesConsumer, RpsConsumer, PenaltyConsumer
from apps.quiz_global.consumers import QuizGlobalConsumer

websocket_urlpatterns = [
    path("ws/quiz-global/<int:game_id>/", QuizGlobalConsumer.as_asgi()),
    path("ws/parties/", PartiesConsumer.as_asgi()),
    path("ws/rps/<str:match_id>/", RpsConsumer.as_asgi()),
    path("ws/penalty/<str:match_id>/", PenaltyConsumer.as_asgi()),
    path("ws/ville/<str:ville_slug>/", CityChatConsumer.as_asgi()),
    path("ws/notifications/", NotificationConsumer.as_asgi()),
]
