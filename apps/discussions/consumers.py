from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncJsonWebsocketConsumer

from apps.discussions.models import Ville, Message


class CityChatConsumer(AsyncJsonWebsocketConsumer):
    """Salon de discussion temps réel par ville (RG-DIS)."""

    async def connect(self):
        self.ville_slug = self.scope["url_route"]["kwargs"].get("ville_slug")
        user = self.scope.get("user")
        if not user or getattr(user, "is_anonymous", True):
            await self.close()
            return
        if not await self._ville_existe(self.ville_slug):
            await self.close()
            return
        self.ville_group = f"ville_{self.ville_slug}"
        await self.channel_layer.group_add(self.ville_group, self.channel_name)
        await self.accept()

    async def disconnect(self, code):
        if hasattr(self, "ville_group") and self.channel_layer is not None:
            await self.channel_layer.group_discard(self.ville_group, self.channel_name)

    async def receive_json(self, content, **kwargs):
        
        contenu = (content.get("contenu") or "").strip()
        utilisateur = self.scope.get("user")
        if not contenu or not utilisateur or getattr(utilisateur, "is_anonymous", True):
            return
        if not hasattr(self, "ville_group"):
            return
        message = await self._enregistrer_message(utilisateur, contenu)
        await self.channel_layer.group_send(
            self.ville_group,
            {
                "type": "chat.message",
                "data": {
                    "id": message.id,
                    "pseudo": message.utilisateur.pseudo,
                    "utilisateur": {"pseudo": message.utilisateur.pseudo},
                    "contenu": message.contenu,
                    "cree_le": message.cree_le.isoformat(),
                },
            },
        )

    async def chat_message(self, event):
        await self.send_json(event["data"])

    @database_sync_to_async
    def _enregistrer_message(self, utilisateur, contenu):
        ville = Ville.objects.get(slug=self.ville_slug)
        return Message.objects.create(ville=ville, utilisateur=utilisateur, contenu=contenu)

    @database_sync_to_async
    def _ville_existe(self, slug):
        return Ville.objects.filter(slug=slug).exists()


class NotificationConsumer(AsyncJsonWebsocketConsumer):
    """Canal dédié aux notifications individuelles."""

    async def connect(self):
        user = self.scope.get("user")
        if not user or getattr(user, "is_anonymous", True):
            await self.close()
            return
        self.user_group = f"notifications_{user.pk}"
        await self.channel_layer.group_add(self.user_group, self.channel_name)
        await self.accept()

    async def disconnect(self, code):
        if hasattr(self, "user_group") and self.channel_layer is not None:
            await self.channel_layer.group_discard(self.user_group, self.channel_name)

    async def receive_json(self, content, **kwargs):
        return

    async def notify(self, event):
        payload = event.get("data", {})
        if not isinstance(payload, dict):
            return
        await self.send_json(payload)
