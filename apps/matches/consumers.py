from channels.generic.websocket import AsyncJsonWebsocketConsumer


class MatchConsumer(AsyncJsonWebsocketConsumer):
    """WebSocket du match — diffusion temps réel des phases (RG-GAM)."""

    async def connect(self):
        self.match_id = self.scope["url_route"]["kwargs"].get("match_id")
        self.match_group = f"match_{self.match_id}"
        await self.channel_layer.group_add(self.match_group, self.channel_name)
        await self.accept()

    async def disconnect(self, code):
        if hasattr(self, "match_group"):
            await self.channel_layer.group_discard(self.match_group, self.channel_name)

    async def receive_json(self, content, **kwargs):
        # Relaie l'intégralité du payload reçu au groupe du match
        # (utile pour des events personnalisés comme `rabbit_join`, `rabbit_move`, `rabbit_win`).
        try:
            await self.channel_layer.group_send(
                self.match_group,
                {
                    "type": "match.event",
                    "data": content,
                },
            )
        except Exception:
            # silences errors when channel layer unavailable (tests/dev without Redis)
            return

    async def match_event(self, event):
        await self.send_json(event["data"])


class PartiesConsumer(AsyncJsonWebsocketConsumer):
    """Canal global pour publier les parties disponibles en temps réel."""

    async def connect(self):
        user = self.scope.get("user")
        # require authenticated users
        if not user or getattr(user, "is_anonymous", True):
            await self.close()
            return
        self.group_name = "parties"
        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()

    async def disconnect(self, code):
        if hasattr(self, "group_name") and self.channel_layer is not None:
            await self.channel_layer.group_discard(self.group_name, self.channel_name)

    async def receive_json(self, content, **kwargs):
        # no-op: clients don't send on this channel
        return

    async def parties_event(self, event):
        await self.send_json(event.get("data", {}))


class RpsConsumer(AsyncJsonWebsocketConsumer):
    """WebSocket dédié aux parties RPS éphemeres."""

    async def connect(self):
        user = self.scope.get("user")
        if not user or getattr(user, "is_anonymous", True):
            await self.close()
            return
        self.match_id = self.scope["url_route"]["kwargs"].get("match_id")
        self.match_group = f"rps_{self.match_id}"
        await self.channel_layer.group_add(self.match_group, self.channel_name)
        await self.accept()

    async def disconnect(self, code):
        if hasattr(self, "match_group") and self.channel_layer is not None:
            await self.channel_layer.group_discard(self.match_group, self.channel_name)

    async def receive_json(self, content, **kwargs):
        if not hasattr(self, "match_group"):
            return
        
        # Gérer les événements de revanche
        event_type = content.get("type")
        if event_type == "rematch_request":
            await self.channel_layer.group_send(
                self.match_group,
                {
                    "type": "rps.event",
                    "data": {
                        "type": "rematch_request",
                        "from_id": content.get("from_id"),
                    },
                },
            )
        elif event_type == "rematch_accepted":
            await self.channel_layer.group_send(
                self.match_group,
                {
                    "type": "rps.event",
                    "data": {
                        "type": "rematch_accepted",
                    },
                },
            )
        elif event_type == "rematch_refused":
            await self.channel_layer.group_send(
                self.match_group,
                {
                    "type": "rps.event",
                    "data": {
                        "type": "rematch_refused",
                    },
                },
            )
        else:
            # Relayer les autres événements
            await self.channel_layer.group_send(
                self.match_group,
                {
                    "type": "rps.event",
                    "data": content,
                },
            )

    async def rps_event(self, event):
        await self.send_json(event.get("data", {}))


class PenaltyConsumer(AsyncJsonWebsocketConsumer):
    async def connect(self):
        user = self.scope.get("user")
        if not user or getattr(user, "is_anonymous", True):
            await self.close()
            return
        self.match_id = self.scope["url_route"]["kwargs"].get("match_id")
        self.match_group = f"penalty_{self.match_id}"
        await self.channel_layer.group_add(self.match_group, self.channel_name)
        await self.accept()

    async def disconnect(self, close_code):
        if hasattr(self, "match_group") and self.channel_layer is not None:
            await self.channel_layer.group_discard(self.match_group, self.channel_name)

    async def receive_json(self, content, **kwargs):
        if not hasattr(self, "match_group"):
            return
        await self.channel_layer.group_send(
            self.match_group,
            {
                "type": "penalty.event",
                "data": content,
            },
        )

    async def penalty_event(self, event):
        await self.send_json(event.get("data", {}))