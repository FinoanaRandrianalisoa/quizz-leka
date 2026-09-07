import asyncio

from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncJsonWebsocketConsumer

from apps.quiz_global.errors import QuizGlobalError
from apps.quiz_global.models import QuizGlobalGame
from apps.quiz_global.services import READING_DURATION, ANSWERING_DURATION, RESULT_DURATION, select_theme, serialize_game, submit_answer, tick


class QuizGlobalConsumer(AsyncJsonWebsocketConsumer):
    async def connect(self):
        user = self.scope.get("user")
        if not user or getattr(user, "is_anonymous", True):
            await self.close()
            return
        self.game_id = self.scope["url_route"]["kwargs"].get("game_id")
        self.user = user
        self.group_name = f"quiz_global_{self.game_id}"
        self.user_group = f"quiz_global_{self.game_id}_u_{user.pk}"
        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.channel_layer.group_add(self.user_group, self.channel_name)
        await self.accept()
        state = await database_sync_to_async(self._state)()
        if state:
            await self.send_json(state)
        await self._arm_local_tick()

    async def disconnect(self, code):
        if hasattr(self, "group_name"):
            await self.channel_layer.group_discard(self.group_name, self.channel_name)
        if hasattr(self, "user_group"):
            await self.channel_layer.group_discard(self.user_group, self.channel_name)

    def _state(self):
        game = QuizGlobalGame.objects.filter(pk=self.game_id).first()
        if game is None:
            return None
        payload = serialize_game(game, self.user)
        payload["event"] = "STATE"
        return payload

    async def receive_json(self, content, **kwargs):
        event = (content.get("event") or content.get("type") or "").upper()
        try:
            if event in {"SELECT_THEME", "THEME_SELECTED"}:
                await database_sync_to_async(select_theme)(
                    self.user,
                    int(self.game_id),
                    int(content.get("theme_id") or content.get("themeId")),
                )
                await self._arm_local_tick()
            elif event in {"PLAYER_ANSWER", "ANSWER"}:
                await database_sync_to_async(submit_answer)(
                    self.user,
                    int(self.game_id),
                    int(content.get("game_question_id") or content.get("gameQuestionId")),
                    content.get("answer") or content.get("selectedOption"),
                )
            elif event in {"RECONNECT", "GET_STATE"}:
                state = await database_sync_to_async(self._state)()
                if state:
                    await self.send_json(state)
            elif event in {"CHAT", "MESSAGE"}:
                await self.channel_layer.group_send(
                    self.group_name,
                    {
                        "type": "quiz.event",
                        "data": {
                            "type": "message",
                            "envoyeur": content.get("envoyeur") or self.user.pseudo,
                            "message": content.get("message") or "",
                        },
                    },
                )
        except QuizGlobalError as exc:
            await self.send_json({"event": "ERROR", "code": exc.code, "message": exc.message})
        except Exception:
            await self.send_json({"event": "ERROR", "code": "INTERNAL_ERROR", "message": "Action refusée."})

    async def quiz_event(self, event):
        await self.send_json(event.get("data", {}))

    async def _arm_local_tick(self):
        game = await database_sync_to_async(lambda: QuizGlobalGame.objects.filter(pk=self.game_id).first())()
        if game is None or not game.phase_deadline:
            return
        delay = max((game.phase_deadline - game.phase_started_at).total_seconds() if game.phase_started_at else 10, 1)
        if game.status == QuizGlobalGame.Status.QUESTION_READING:
            delay = READING_DURATION.total_seconds()
        elif game.status == QuizGlobalGame.Status.ANSWERING:
            delay = ANSWERING_DURATION.total_seconds()
        elif game.status == QuizGlobalGame.Status.QUESTION_FINISHED:
            delay = RESULT_DURATION.total_seconds()
        asyncio.create_task(self._delayed_tick(delay))

    async def _delayed_tick(self, delay: float):
        await asyncio.sleep(delay + 0.05)
        try:
            await database_sync_to_async(tick)(int(self.game_id))
        except Exception:
            return
