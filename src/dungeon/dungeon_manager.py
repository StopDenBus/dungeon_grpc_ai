"""
Dungeon Manager - Verwaltet das gesamte Dungeon-Game
"""
import asyncio
from typing import Dict, Optional, List
from datetime import datetime
from .models import Player, Room, Item, NPC, Direction


class DungeonManager:
    """
    Zentrale Verwaltung des Dungeons mit allen Räumen, Spielern und Entities
    """

    def __init__(self):
        self.players: Dict[str, Player] = {}
        self.rooms: Dict[str, Room] = {}
        self.event_queues: Dict[str, asyncio.Queue] = {}
        self._lock = asyncio.Lock()
        self._initialize_dungeon()

    def _initialize_dungeon(self):
        """Initialisiert das Dungeon mit Räumen, Items und NPCs"""

        # Erstelle Räume
        entrance = Room(
            name="Dungeon Eingang",
            description="Ein dunkler Eingang zu einem uralten Dungeon. Fackeln flackern an den Wänden."
        )

        hall = Room(
            name="Große Halle",
            description="Eine geräumige Halle mit hohen Decken. Echos hallen durch den Raum."
        )

        treasury = Room(
            name="Schatzkammer",
            description="Eine glitzernde Kammer voller Gold und Juwelen. Ein schwacher Geruch von Magie liegt in der Luft."
        )

        armory = Room(
            name="Waffenkammer",
            description="Alte Waffen und Rüstungen hängen an den Wänden. Viele sind verrostet."
        )

        dungeon = Room(
            name="Kerker",
            description="Ein feuchter, düsterer Kerker. Ketten hängen von der Decke."
        )

        # Verbinde Räume
        entrance.add_exit(Direction.NORTH, hall)
        hall.add_exit(Direction.SOUTH, entrance)
        hall.add_exit(Direction.EAST, treasury)
        hall.add_exit(Direction.WEST, armory)
        hall.add_exit(Direction.NORTH, dungeon)
        treasury.add_exit(Direction.WEST, hall)
        armory.add_exit(Direction.EAST, hall)
        dungeon.add_exit(Direction.SOUTH, hall)

        # Füge Items hinzu
        entrance.add_item(Item(
            name="Fackel",
            description="Eine brennende Fackel, die helles Licht spendet.",
            value=5
        ))

        treasury.add_item(Item(
            name="Goldmünze",
            description="Eine glänzende Goldmünze mit einem unbekannten Wappen.",
            value=100
        ))

        treasury.add_item(Item(
            name="Magischer Kristall",
            description="Ein funkelnder Kristall, der mit magischer Energie pulsiert.",
            value=500
        ))

        armory.add_item(Item(
            name="Rostiges Schwert",
            description="Ein altes Schwert, verrostet aber noch verwendbar.",
            value=50
        ))

        # Füge NPCs hinzu
        hall.add_npc(NPC(
            name="Wächter",
            description="Ein alter Wächter in zerschlissener Rüstung.",
            health=50,
            is_hostile=False,
            dialogue="Willkommen, Reisender. Sei vorsichtig in diesen Hallen..."
        ))

        treasury.add_npc(NPC(
            name="Schatzdrache",
            description="Ein kleiner Drache, der den Schatz bewacht.",
            health=100,
            is_hostile=True,
            dialogue="GRRR! Mein Schatz!"
        ))

        dungeon.add_npc(NPC(
            name="Gefangener",
            description="Ein magerer Gefangener, gefangen in Ketten.",
            health=30,
            is_hostile=False,
            dialogue="Bitte hilf mir... Ich bin hier seit Jahren gefangen..."
        ))

        # Speichere Räume
        for room in [entrance, hall, treasury, armory, dungeon]:
            self.rooms[room.room_id] = room

        # Setze Eingangsraum als Standard
        self.entrance_room = entrance

    async def register_player(self, player_name: str) -> Player:
        """Registriert einen neuen Spieler"""
        async with self._lock:
            player = Player(name=player_name, current_room=self.entrance_room)
            self.players[player.player_id] = player
            self.entrance_room.add_player(player)
            self.event_queues[player.player_id] = asyncio.Queue()

            # Broadcast Event
            await self._broadcast_event(
                "PLAYER_JOINED",
                f"{player_name} hat das Dungeon betreten!",
                self.entrance_room.room_id
            )

            return player

    async def unregister_player(self, player_id: str) -> tuple[bool, str]:
        """Entfernt einen Spieler aus dem Spiel"""
        player = await self.get_player(player_id)
        if not player:
            return False, "Spieler nicht gefunden."

        async with self._lock:
            player_name = player.name
            current_room = player.current_room

            # Entferne Spieler aus aktuellem Raum
            if current_room:
                current_room.remove_player(player)

                # Broadcast Event an Raum
                await self._broadcast_event(
                    "PLAYER_LEFT",
                    f"{player_name} hat das Dungeon verlassen.",
                    current_room.room_id
                )

            # Entferne Spieler aus der Spielerliste
            if player_id in self.players:
                del self.players[player_id]

            # Entferne Event Queue
            if player_id in self.event_queues:
                del self.event_queues[player_id]

            return True, f"{player_name} wurde abgemeldet."

    async def get_player(self, player_id: str) -> Optional[Player]:
        """Gibt Spieler zurück"""
        return self.players.get(player_id)

    async def move_player(self, player_id: str, direction_str: str) -> tuple[bool, str, Optional[Room]]:
        """Bewegt einen Spieler in eine Richtung"""
        player = await self.get_player(player_id)
        if not player:
            return False, "Spieler nicht gefunden.", None

        try:
            direction = Direction(direction_str.lower())
        except ValueError:
            return False, f"Ungültige Richtung: {direction_str}", None

        async with self._lock:
            old_room = player.current_room
            new_room = await player.move_to(direction)

            if new_room:
                await self._broadcast_event(
                    "PLAYER_MOVED",
                    f"{player.name} ist gegangen.",
                    old_room.room_id if old_room else ""
                )
                await self._broadcast_event(
                    "PLAYER_MOVED",
                    f"{player.name} ist angekommen.",
                    new_room.room_id
                )
                return True, f"Du bewegst dich nach {direction_str}.", new_room
            else:
                return False, f"Es gibt keinen Ausgang in Richtung {direction_str}.", None

    async def take_item(self, player_id: str, item_id: str) -> tuple[bool, str]:
        """Spieler nimmt Item auf"""
        player = await self.get_player(player_id)
        if not player:
            return False, "Spieler nicht gefunden."

        async with self._lock:
            item = await player.take_item(item_id)
            if item:
                await self._broadcast_event(
                    "ITEM_TAKEN",
                    f"{player.name} hat {item.name} aufgenommen.",
                    player.current_room.room_id if player.current_room else ""
                )
                return True, f"Du hast {item.name} aufgenommen."
            else:
                return False, "Item nicht gefunden."

    async def drop_item(self, player_id: str, item_id: str) -> tuple[bool, str]:
        """Spieler legt Item ab"""
        player = await self.get_player(player_id)
        if not player:
            return False, "Spieler nicht gefunden."

        async with self._lock:
            item = await player.drop_item(item_id)
            if item:
                await self._broadcast_event(
                    "ITEM_DROPPED",
                    f"{player.name} hat {item.name} abgelegt.",
                    player.current_room.room_id if player.current_room else ""
                )
                return True, f"Du hast {item.name} abgelegt."
            else:
                return False, "Item nicht im Inventar gefunden."

    async def talk_to_npc(self, player_id: str, npc_id: str) -> tuple[bool, str, str]:
        """Spieler spricht mit NPC"""
        player = await self.get_player(player_id)
        if not player or not player.current_room:
            return False, "Spieler nicht gefunden.", ""

        npc = player.current_room.get_npc(npc_id)
        if not npc:
            return False, "NPC nicht gefunden.", ""

        response = await npc.talk()
        return True, f"Du sprichst mit {npc.name}.", response

    async def attack_npc(self, player_id: str, npc_id: str) -> tuple[bool, str, int, int]:
        """Spieler greift NPC an"""
        player = await self.get_player(player_id)
        if not player or not player.current_room:
            return False, "Spieler nicht gefunden.", 0, 0

        npc = player.current_room.get_npc(npc_id)
        if not npc:
            return False, "NPC nicht gefunden.", 0, 0

        async with self._lock:
            success, damage, health = await player.attack_npc(npc_id)

            if success:
                if health <= 0:
                    await self._broadcast_event(
                        "NPC_DIED",
                        f"{player.name} hat {npc.name} besiegt!",
                        player.current_room.room_id
                    )
                    return True, f"Du hast {npc.name} besiegt!", damage, health
                else:
                    await self._broadcast_event(
                        "NPC_ATTACKED",
                        f"{player.name} greift {npc.name} an!",
                        player.current_room.room_id
                    )
                    return True, f"Du hast {npc.name} {damage} Schaden zugefügt.", damage, health
            else:
                return False, "Angriff fehlgeschlagen.", 0, 0

    async def _broadcast_event(self, event_type: str, message: str, room_id: str, sender_name: str = ""):
        """Sendet Event an alle Spieler im Raum"""
        from . import dungeon_pb2

        event = dungeon_pb2.GameEvent(
            event_type=getattr(dungeon_pb2.GameEvent.EventType, event_type),
            message=message,
            room_id=room_id,
            timestamp=int(datetime.now().timestamp()),
            sender_name=sender_name
        )

        # Sende an alle Spieler im Raum
        for player in self.players.values():
            if player.current_room and player.current_room.room_id == room_id:
                if player.player_id in self.event_queues:
                    await self.event_queues[player.player_id].put(event)

    async def _send_event_to_player(self, player_id: str, event_type: str, message: str, sender_name: str = ""):
        """Sendet Event an einen spezifischen Spieler"""
        from . import dungeon_pb2

        event = dungeon_pb2.GameEvent(
            event_type=getattr(dungeon_pb2.GameEvent.EventType, event_type),
            message=message,
            room_id="",
            timestamp=int(datetime.now().timestamp()),
            sender_name=sender_name
        )

        if player_id in self.event_queues:
            await self.event_queues[player_id].put(event)

    async def _broadcast_to_all(self, event_type: str, message: str, sender_name: str = ""):
        """Sendet Event an alle Spieler"""
        from . import dungeon_pb2

        event = dungeon_pb2.GameEvent(
            event_type=getattr(dungeon_pb2.GameEvent.EventType, event_type),
            message=message,
            room_id="",
            timestamp=int(datetime.now().timestamp()),
            sender_name=sender_name
        )

        for player_id in self.event_queues:
            await self.event_queues[player_id].put(event)

    async def send_direct_message(self, sender_id: str, recipient_name: str, message: str) -> tuple[bool, str]:
        """Sendet direkte Nachricht an einen Spieler"""
        sender = await self.get_player(sender_id)
        if not sender:
            return False, "Sender nicht gefunden."

        # Finde Empfänger
        recipient = None
        for player in self.players.values():
            if player.name.lower() == recipient_name.lower():
                recipient = player
                break

        if not recipient:
            return False, f"Spieler '{recipient_name}' nicht gefunden."

        # Sende Nachricht an Empfänger
        await self._send_event_to_player(
            recipient.player_id,
            "DIRECT_MESSAGE",
            f"[Direktnachricht von {sender.name}]: {message}",
            sender.name
        )

        return True, f"Nachricht an {recipient.name} gesendet."

    async def send_room_message(self, sender_id: str, message: str) -> tuple[bool, str]:
        """Sendet Nachricht an alle Spieler im Raum"""
        sender = await self.get_player(sender_id)
        if not sender or not sender.current_room:
            return False, "Sender nicht gefunden oder nicht in einem Raum."

        await self._broadcast_event(
            "ROOM_MESSAGE",
            f"[{sender.name}]: {message}",
            sender.current_room.room_id,
            sender.name
        )

        return True, "Nachricht an Raum gesendet."

    async def send_broadcast_message(self, sender_id: str, message: str) -> tuple[bool, str]:
        """Sendet Nachricht an alle Spieler"""
        sender = await self.get_player(sender_id)
        if not sender:
            return False, "Sender nicht gefunden."

        await self._broadcast_to_all(
            "BROADCAST_MESSAGE",
            f"[BROADCAST - {sender.name}]: {message}",
            sender.name
        )

        return True, "Broadcast gesendet."

    async def get_online_players(self) -> List[tuple[str, str]]:
        """Gibt Liste aller Online-Spieler zurück"""
        players_info = []
        for player in self.players.values():
            room_name = player.current_room.name if player.current_room else "Unbekannt"
            players_info.append((player.name, room_name))
        return players_info

    async def get_events(self, player_id: str) -> asyncio.Queue:
        """Gibt Event Queue für Spieler zurück"""
        if player_id not in self.event_queues:
            self.event_queues[player_id] = asyncio.Queue()
        return self.event_queues[player_id]
