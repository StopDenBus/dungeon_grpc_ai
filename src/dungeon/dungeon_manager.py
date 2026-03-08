"""
Dungeon Manager - Verwaltet das gesamte Dungeon-Game
"""

import asyncio
from typing import Dict, Optional, List, Tuple
from datetime import datetime
from .models import Player, Room, Item, NPC, Direction, Chest, Spell, Weapon


class DungeonManager:
    """
    Zentrale Verwaltung des Dungeons mit allen Räumen, Spielern und Entities
    """

    def __init__(self):
        self.players: Dict[str, Player] = {}
        self.rooms: Dict[str, Room] = {}
        self.event_queues: Dict[str, asyncio.Queue] = {}
        self._lock = asyncio.Lock()
        self.available_spells: Dict[str, Spell] = {}  # Alle verfügbaren Zaubersprüche
        self._initialize_dungeon()

    def _parse_item_name(self, item_input: str) -> Tuple[str, int]:
        """Parst Item-Eingabe in Namen und optionalen Index.

        Beispiele:
        - 'fackel' -> ('fackel', 1)
        - 'fackel 2' -> ('fackel', 2)
        - 'goldmünze' -> ('goldmünze', 1)
        """
        parts = item_input.strip().split()
        if len(parts) >= 2 and parts[-1].isdigit():
            index = int(parts[-1])
            name = " ".join(parts[:-1])
            return (name, index)
        return (item_input.strip(), 1)

    def _initialize_dungeon(self):
        """Initialisiert das Dungeon mit Räumen, Items und NPCs"""

        # Definiere Zaubersprüche
        fireball = Spell(
            name="Feuerball",
            description="Ein mächtiger Feuerball, der dem Gegner großen Schaden zufügt.",
            mana_cost=30,
            damage=50,
        )

        fire_orb = Spell(
            name="Feuerkugel",
            description="Eine brennende Feuerkugel, die mittleren Schaden verursacht.",
            mana_cost=20,
            damage=35,
        )

        fire_spark = Spell(
            name="Feuerfunke",
            description="Ein kleiner Feuerfunke, der leichten Schaden verursacht.",
            mana_cost=10,
            damage=15,
        )

        # Speichere verfügbare Zaubersprüche
        self.available_spells["feuerball"] = fireball
        self.available_spells["feuerkugel"] = fire_orb
        self.available_spells["feuerfunke"] = fire_spark

        # Erstelle Räume
        entrance = Room(
            name="Dungeon Eingang",
            description="Ein dunkler Eingang zu einem uralten Dungeon. Fackeln flackern an den Wänden.",
        )

        hall = Room(
            name="Große Halle",
            description="Eine geräumige Halle mit hohen Decken. Echos hallen durch den Raum.",
        )

        treasury = Room(
            name="Schatzkammer",
            description="Eine glitzernde Kammer voller Gold und Juwelen. Ein schwacher Geruch von Magie liegt in der Luft.",
            guarded_by=["Schatzdrache"],
        )

        armory = Room(
            name="Waffenkammer",
            description="Alte Waffen und Rüstungen hängen an den Wänden. Viele sind verrostet.",
        )

        dungeon = Room(
            name="Kerker",
            description="Ein feuchter, düsterer Kerker. Ketten hängen von der Decke.",
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
        entrance.add_item(
            Item(
                name="Fackel",
                description="Eine brennende Fackel, die helles Licht spendet.",
                value=5,
            )
        )

        # Zauberspruchrolle: Feuerfunke in Große Halle
        hall.add_item(
            Item(
                name="Zauberspruchrolle",
                description="Eine alte Schriftrolle mit dem Zauber 'Feuerfunke' darauf.",
                value=50,
                item_type="scroll",
                spell_name="Feuerfunke",
            )
        )

        treasury.add_item(
            Item(
                name="Goldmünze",
                description="Eine glänzende Goldmünze mit einem unbekannten Wappen.",
                value=100,
            )
        )

        treasury.add_item(
            Item(
                name="Magischer Kristall",
                description="Ein funkelnder Kristall, der mit magischer Energie pulsiert.",
                value=500,
            )
        )

        armory.add_item(
            Item(
                name="Rostiges Schwert",
                description="Ein altes Schwert, verrostet aber noch verwendbar.",
                value=50,
            )
        )

        # Füge NPCs hinzu
        hall.add_npc(
            NPC(
                name="Wächter",
                description="Ein alter Wächter in zerschlissener Rüstung.",
                health=50,
                is_hostile=False,
                dialogue="Willkommen, Reisender. Sei vorsichtig in diesen Hallen...",
            )
        )

        treasury.add_npc(
            NPC(
                name="Schatzdrache",
                description="Ein kleiner Drache, der den Schatz bewacht.",
                health=100,
                is_hostile=True,
                dialogue="GRRR! Mein Schatz!",
                spell_cast_probability=0.5,  # 50% Chance bei jedem Angriff zu zaubern
            )
        )
        # Drache bekommt Feuerball-Zauber und Feuerkugel
        treasury.npcs[0].spellbook.add_spell(fireball)
        treasury.npcs[0].spellbook.add_spell(fire_orb)

        dungeon.add_npc(
            NPC(
                name="Gefangener",
                description="Ein magerer Gefangener, gefangen in Ketten.",
                health=30,
                is_hostile=False,
                dialogue="Bitte hilf mir... Ich bin hier seit Jahren gefangen...",
            )
        )

        # Füge Kisten hinzu
        entrance_chest = Chest(
            name="Holzkiste", description="Eine alte, verwitterte Holzkiste."
        )
        entrance_chest.items.append(
            Item(
                name="Seil",
                description="Ein robustes Seil, etwa 10 Meter lang.",
                value=10,
            )
        )
        # Zauberbuch in Startraum-Kiste
        entrance_chest.items.append(
            Item(
                name="Zauberbuch",
                description="Ein ledergebundenes Buch für Zaubersprüche. Derzeit leer.",
                value=100,
                item_type="spellbook",
            )
        )
        entrance_chest.items.append(
            Weapon(
                name="Messer",
                description="Ein kleines, scharfes Messer. Nützlich im Nahkampf.",
                value=25,
                damage=10,
            )
        )

        entrance.add_chest(entrance_chest)

        treasury_chest = Chest(
            name="Schatztruhe",
            description="Eine prachtvolle, mit Gold verzierte Truhe.",
            is_open=False,
        )
        treasury_chest.items.append(
            Item(
                name="Diamant",
                description="Ein lupenreiner, funkelnder Diamant.",
                value=1000,
            )
        )
        treasury_chest.items.append(
            Item(
                name="Diamant",
                description="Ein weiterer glänzender Diamant, etwas kleiner.",
                value=800,
            )
        )
        treasury_chest.items.append(
            Item(
                name="Rubin",
                description="Ein tiefroter Rubin von außergewöhnlicher Qualität.",
                value=750,
            )
        )
        treasury.add_chest(treasury_chest)

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
                self.entrance_room.room_id,
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
                    current_room.room_id,
                )

            # Entferne Spieler aus der Spielerliste
            if player_id in self.players:
                del self.players[player_id]

            # Entferne Event Queue
            if player_id in self.event_queues:
                del self.event_queues[player_id]

            return True, f"{player_name} wurde abgemeldet."

    async def get_player(self, player_id: str) -> Optional[Player]:
        """Gibt Spieler anhand der player_id zurück"""
        return self.players.get(player_id)

    def get_player_by_name(self, player_name: str) -> Optional[Player]:
        """Gibt den aktiven Spieler anhand des Namens zurück."""
        for player in self.players.values():
            if player.name == player_name:
                return player
        return None

    async def move_player(
        self, player_id: str, direction_str: str
    ) -> tuple[bool, str, Optional[Room]]:
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
                    old_room.room_id if old_room else "",
                )
                await self._broadcast_event(
                    "PLAYER_MOVED", f"{player.name} ist angekommen.", new_room.room_id
                )
                return True, f"Du bewegst dich nach {direction_str}.", new_room
            else:
                return (
                    False,
                    f"Es gibt keinen Ausgang in Richtung {direction_str}.",
                    None,
                )

    async def take_item(self, player_id: str, item_input: str) -> tuple[bool, str]:
        """Spieler nimmt Item auf (nach Namen und optionalem Index)"""
        player = await self.get_player(player_id)
        if not player:
            return False, "Spieler nicht gefunden."

        item_name, index = self._parse_item_name(item_input)

        # Prüfe zuerst ob Raum oder Item bewacht wird
        if player.current_room:
            # Prüfe Raum-Bewachung
            if player.current_room.guarded_by:
                for guard_name in player.current_room.guarded_by:
                    for npc in player.current_room.npcs:
                        if npc.name == guard_name and npc.is_alive():
                            return (
                                False,
                                f"{npc.name} bewacht diesen Raum und verhindert, dass du etwas nimmst! Du musst {npc.name} zuerst besiegen.",
                            )

            # Prüfe Item-spezifische Bewachung
            item_to_check = player.current_room.get_item_by_name(item_name, index)
            if item_to_check and item_to_check.guarded_by:
                for guard_name in item_to_check.guarded_by:
                    for npc in player.current_room.npcs:
                        if npc.name == guard_name and npc.is_alive():
                            return (
                                False,
                                f"{npc.name} bewacht {item_to_check.name} und verhindert, dass du es nimmst! Du musst {npc.name} zuerst besiegen.",
                            )

        async with self._lock:
            item = await player.take_item(item_name, index)
            if item:
                await self._broadcast_event(
                    "ITEM_TAKEN",
                    f"{player.name} hat {item.name} aufgenommen.",
                    player.current_room.room_id if player.current_room else "",
                )
                return True, f"Du hast {item.name} aufgenommen."
            else:
                if index > 1:
                    return False, f"Es gibt kein {index}. '{item_name}' hier."
                else:
                    return False, f"'{item_name}' nicht gefunden."

    async def drop_item(self, player_id: str, item_input: str) -> tuple[bool, str]:
        """Spieler legt Item ab (nach Namen und optionalem Index)"""
        player = await self.get_player(player_id)
        if not player:
            return False, "Spieler nicht gefunden."

        item_name, index = self._parse_item_name(item_input)

        async with self._lock:
            item = await player.drop_item(item_name, index)
            if item:
                await self._broadcast_event(
                    "ITEM_DROPPED",
                    f"{player.name} hat {item.name} abgelegt.",
                    player.current_room.room_id if player.current_room else "",
                )
                return True, f"Du hast {item.name} abgelegt."
            else:
                if index > 1:
                    return False, f"Du hast kein {index}. '{item_name}' im Inventar."
                else:
                    return False, f"'{item_name}' nicht im Inventar gefunden."

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

    async def attack_npc(
        self, player_id: str, npc_id: str
    ) -> tuple[bool, str, int, int]:
        """Spieler greift NPC an"""
        import random

        player = await self.get_player(player_id)
        if not player or not player.current_room:
            return False, "Spieler nicht gefunden.", 0, 0

        npc = player.current_room.get_npc(npc_id)
        if not npc:
            return False, "NPC nicht gefunden.", 0, 0

        async with self._lock:
            success, damage, health = await player.attack_npc(npc_id)

            if success:
                message = ""
                if health <= 0:
                    await self._broadcast_event(
                        "NPC_DIED",
                        f"{player.name} hat {npc.name} besiegt!",
                        player.current_room.room_id,
                    )
                    message = f"Du hast {npc.name} besiegt!"
                else:
                    await self._broadcast_event(
                        "NPC_ATTACKED",
                        f"{player.name} greift {npc.name} an!",
                        player.current_room.room_id,
                    )
                    message = f"Du hast {npc.name} {damage} Schaden zugefügt."

                    # NPC Gegenzauber
                    if npc.is_alive() and npc.spell_cast_probability > 0:
                        # Prüfe ob NPC zurückzaubert
                        if random.random() < npc.spell_cast_probability:
                            spells = npc.spellbook.list_spells()
                            if spells and npc.magic >= min(s.mana_cost for s in spells):
                                # Wähle zufälligen Zauber, den sich der NPC leisten kann
                                affordable_spells = [
                                    s for s in spells if s.mana_cost <= npc.magic
                                ]
                                if affordable_spells:
                                    spell = random.choice(affordable_spells)
                                    npc.magic -= spell.mana_cost

                                    # Füge Schaden zum Spieler hinzu
                                    player_damage = await player.take_damage(
                                        spell.damage
                                    )

                                    await self._broadcast_event(
                                        "SPELL_CAST",
                                        f"{npc.name} wirkt '{spell.name}' auf {player.name}!",
                                        player.current_room.room_id,
                                    )

                                    message += f"\n💥 {npc.name} kontert mit '{spell.name}'! Du erleidest {spell.damage} Schaden. Verbleibende HP: {player.health}"

                return True, message, damage, health
            else:
                return False, "Angriff fehlgeschlagen.", 0, 0

    async def _broadcast_event(
        self, event_type: str, message: str, room_id: str, sender_name: str = ""
    ):
        """Sendet Event an alle Spieler im Raum"""
        from . import dungeon_pb2

        event = dungeon_pb2.GameEvent(
            event_type=getattr(dungeon_pb2.GameEvent.EventType, event_type),
            message=message,
            room_id=room_id,
            timestamp=int(datetime.now().timestamp()),
            sender_name=sender_name,
        )

        # Sende an alle Spieler im Raum
        for player in self.players.values():
            if player.current_room and player.current_room.room_id == room_id:
                if player.player_id in self.event_queues:
                    await self.event_queues[player.player_id].put(event)

    async def _send_event_to_player(
        self, player_id: str, event_type: str, message: str, sender_name: str = ""
    ):
        """Sendet Event an einen spezifischen Spieler"""
        from . import dungeon_pb2

        event = dungeon_pb2.GameEvent(
            event_type=getattr(dungeon_pb2.GameEvent.EventType, event_type),
            message=message,
            room_id="",
            timestamp=int(datetime.now().timestamp()),
            sender_name=sender_name,
        )

        if player_id in self.event_queues:
            await self.event_queues[player_id].put(event)

    async def _broadcast_to_all(
        self, event_type: str, message: str, sender_name: str = ""
    ):
        """Sendet Event an alle Spieler"""
        from . import dungeon_pb2

        event = dungeon_pb2.GameEvent(
            event_type=getattr(dungeon_pb2.GameEvent.EventType, event_type),
            message=message,
            room_id="",
            timestamp=int(datetime.now().timestamp()),
            sender_name=sender_name,
        )

        for player_id in self.event_queues:
            await self.event_queues[player_id].put(event)

    async def send_direct_message(
        self, sender_id: str, recipient_name: str, message: str
    ) -> tuple[bool, str]:
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
            sender.name,
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
            sender.name,
        )

        return True, "Nachricht an Raum gesendet."

    async def send_broadcast_message(
        self, sender_id: str, message: str
    ) -> tuple[bool, str]:
        """Sendet Nachricht an alle Spieler"""
        sender = await self.get_player(sender_id)
        if not sender:
            return False, "Sender nicht gefunden."

        await self._broadcast_to_all(
            "BROADCAST_MESSAGE", f"[BROADCAST - {sender.name}]: {message}", sender.name
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

    async def open_chest(self, player_id: str, chest_input: str) -> tuple[bool, str]:
        """Öffnet eine Kiste"""
        player = await self.get_player(player_id)
        if not player or not player.current_room:
            return False, "Spieler nicht gefunden."

        chest_name, index = self._parse_item_name(chest_input)

        # Prüfe zuerst ob Raum oder Kiste bewacht wird
        if player.current_room:
            # Prüfe Raum-Bewachung
            if player.current_room.guarded_by:
                for guard_name in player.current_room.guarded_by:
                    for npc in player.current_room.npcs:
                        if npc.name == guard_name and npc.is_alive():
                            return (
                                False,
                                f"{npc.name} bewacht diesen Raum und verhindert, dass du etwas öffnest! Du musst {npc.name} zuerst besiegen.",
                            )

        # Prüfe Kisten-spezifische Bewachung
        chest_to_check = player.current_room.get_chest_by_name(chest_name, index)
        if chest_to_check and chest_to_check.guarded_by:
            for guard_name in chest_to_check.guarded_by:
                for npc in player.current_room.npcs:
                    if npc.name == guard_name and npc.is_alive():
                        return (
                            False,
                            f"{npc.name} bewacht {chest_to_check.name} und verhindert, dass du sie öffnest! Du musst {npc.name} zuerst besiegen.",
                        )

        async with self._lock:
            chest = player.current_room.get_chest_by_name(chest_name, index)
            if not chest:
                if index > 1:
                    return False, f"Es gibt keine {index}. '{chest_name}' hier."
                return False, f"'{chest_name}' nicht gefunden."

            success, message = chest.open()
            if success:
                await self._broadcast_event(
                    "CHEST_OPENED",
                    f"{player.name} öffnet {chest.name}.",
                    player.current_room.room_id,
                )
            return success, message

    async def close_chest(self, player_id: str, chest_input: str) -> tuple[bool, str]:
        """Schließt eine Kiste"""
        player = await self.get_player(player_id)
        if not player or not player.current_room:
            return False, "Spieler nicht gefunden."

        chest_name, index = self._parse_item_name(chest_input)

        async with self._lock:
            chest = player.current_room.get_chest_by_name(chest_name, index)
            if not chest:
                if index > 1:
                    return False, f"Es gibt keine {index}. '{chest_name}' hier."
                return False, f"'{chest_name}' nicht gefunden."

            success, message = chest.close()
            if success:
                await self._broadcast_event(
                    "CHEST_CLOSED",
                    f"{player.name} schließt {chest.name}.",
                    player.current_room.room_id,
                )
            return success, message

    async def put_in_chest(
        self, player_id: str, item_input: str, chest_input: str
    ) -> tuple[bool, str]:
        """Legt Item in Kiste"""
        player = await self.get_player(player_id)
        if not player or not player.current_room:
            return False, "Spieler nicht gefunden."

        item_name, item_index = self._parse_item_name(item_input)
        chest_name, chest_index = self._parse_item_name(chest_input)

        async with self._lock:
            chest = player.current_room.get_chest_by_name(chest_name, chest_index)
            if not chest:
                return False, f"'{chest_name}' nicht gefunden."

            # Entferne Item aus Inventar
            item = await player.drop_item(item_name, item_index)
            if not item:
                if item_index > 1:
                    return (
                        False,
                        f"Du hast kein {item_index}. '{item_name}' im Inventar.",
                    )
                return False, f"'{item_name}' nicht im Inventar gefunden."

            # Lege in Kiste (Item wurde schon aus Inventar entfernt und in Raum gelegt)
            # Wir müssen es erst aus dem Raum wieder entfernen
            player.current_room.items.remove(item)

            success, message = chest.add_item(item)
            if not success:
                # Wenn fehlgeschlagen, Item zurück ins Inventar
                player.inventory.append(item)
                return False, message

            await self._broadcast_event(
                "ITEM_PUT_IN_CHEST",
                f"{player.name} legt {item.name} in {chest.name}.",
                player.current_room.room_id,
            )
            return True, f"Du legst {item.name} in {chest.name}."

    async def get_from_chest(
        self, player_id: str, item_input: str, chest_input: str
    ) -> tuple[bool, str]:
        """Holt Item aus Kiste"""
        player = await self.get_player(player_id)
        if not player or not player.current_room:
            return False, "Spieler nicht gefunden."

        item_name, item_index = self._parse_item_name(item_input)
        chest_name, chest_index = self._parse_item_name(chest_input)

        async with self._lock:
            chest = player.current_room.get_chest_by_name(chest_name, chest_index)
            if not chest:
                return False, f"'{chest_name}' nicht gefunden."

            if not chest.is_open:
                return False, f"{chest.name} ist geschlossen. Du musst sie erst öffnen."

            item = chest.remove_item_by_name(item_name, item_index)
            if not item:
                if item_index > 1:
                    return (
                        False,
                        f"Es gibt kein {item_index}. '{item_name}' in {chest.name}.",
                    )
                return False, f"'{item_name}' ist nicht in {chest.name}."

            player.inventory.append(item)

            await self._broadcast_event(
                "ITEM_TAKEN_FROM_CHEST",
                f"{player.name} nimmt {item.name} aus {chest.name}.",
                player.current_room.room_id,
            )
            return True, f"Du nimmst {item.name} aus {chest.name}."

    async def inspect_chest(
        self, player_id: str, chest_input: str
    ) -> tuple[bool, str, Optional[Chest]]:
        """Inspiziert eine Kiste"""
        import logging

        logger = logging.getLogger(__name__)

        logger.info(
            f"[DEBUG DM] inspect_chest called with player_id={player_id}, chest_input={chest_input}"
        )

        player = await self.get_player(player_id)
        if not player or not player.current_room:
            logger.info(f"[DEBUG DM] Player not found or no room")
            return False, "Spieler nicht gefunden.", None

        chest_name, index = self._parse_item_name(chest_input)
        logger.info(f"[DEBUG DM] Parsed: chest_name={chest_name}, index={index}")

        chest = player.current_room.get_chest_by_name(chest_name, index)
        logger.info(f"[DEBUG DM] Found chest: {chest}")

        if not chest:
            if index > 1:
                return False, f"Es gibt keine {index}. '{chest_name}' hier.", None
            return False, f"'{chest_name}' nicht gefunden.", None

        logger.info(
            f"[DEBUG DM] Chest details: name={chest.name}, is_open={chest.is_open}, items count={len(chest.items)}"
        )

        status = "geöffnet" if chest.is_open else "geschlossen"
        description = f"{chest.name}: {chest.description}\nStatus: {status}"

        if chest.is_open:
            if chest.items:
                description += f"\nInhalt ({len(chest.items)} Items):"
            else:
                description += "\nDie Kiste ist leer."
        else:
            description += "\nDu musst die Kiste erst öffnen, um den Inhalt zu sehen."

        logger.info(f"[DEBUG DM] Returning chest object: {chest}")
        return True, description, chest

    async def read_scroll(self, player_id: str, item_input: str) -> tuple[bool, str]:
        """Liest eine Zauberspruchrolle und lernt den Zauber"""
        player = await self.get_player(player_id)
        if not player:
            return False, "Spieler nicht gefunden."

        item_name, index = self._parse_item_name(item_input)

        # Suche Rolle im Inventar
        matching_indices = [
            i
            for i, item in enumerate(player.inventory)
            if item.name.lower() == item_name.lower()
        ]
        if not (0 < index <= len(matching_indices)):
            if index > 1:
                return False, f"Du hast keine {index}. '{item_name}' im Inventar."
            return False, f"'{item_name}' nicht im Inventar gefunden."

        actual_index = matching_indices[index - 1]
        scroll = player.inventory[actual_index]

        # Prüfe ob es eine Zauberspruchrolle ist
        if scroll.item_type != "scroll":
            return False, f"{scroll.name} ist keine Zauberspruchrolle."

        if not scroll.spell_name:
            return False, f"Diese Rolle enthält keinen Zauberspruch."

        # Prüfe ob Spieler ein Zauberbuch im Inventar hat
        has_spellbook = any(item.item_type == "spellbook" for item in player.inventory)
        if not has_spellbook:
            return (
                False,
                "Du brauchst ein Zauberbuch, um Zaubersprüche zu lernen! Finde eines in der Welt.",
            )

        # Hole Spell aus available_spells
        spell = self.available_spells.get(scroll.spell_name.lower())
        if not spell:
            return False, f"Unbekannter Zauberspruch: {scroll.spell_name}"

        # Versuche Zauber zu lernen
        if not player.spellbook.add_spell(spell):
            return False, f"Du kennst '{spell.name}' bereits."

        # Entferne Rolle aus Inventar (wird beim Lesen verbraucht)
        async with self._lock:
            player.inventory.pop(actual_index)

        await self._broadcast_event(
            "SPELL_LEARNED",
            f"{player.name} hat den Zauberspruch '{spell.name}' gelernt!",
            player.current_room.room_id if player.current_room else "",
        )

        return (
            True,
            f"Du liest die Rolle und lernst den Zauberspruch '{spell.name}'! (Manakosten: {spell.mana_cost}, Schaden: {spell.damage})",
        )

    async def cast_spell(
        self, player_id: str, spell_name: str, target_id: str = ""
    ) -> tuple[bool, str, int, int]:
        """Zaubert einen Spruch. Returns (success, message, damage, target_health)"""
        import random

        player = await self.get_player(player_id)
        if not player or not player.current_room:
            return False, "Spieler nicht gefunden.", 0, 0

        # Prüfe ob Spieler den Zauber kennt
        spell = player.spellbook.get_spell(spell_name)
        if not spell:
            return (
                False,
                f"Du kennst den Zauberspruch '{spell_name}' nicht. Nutze 'spellbook' um deine Zauber zu sehen.",
                0,
                0,
            )

        # Prüfe ob genug Mana vorhanden ist
        if player.magic < spell.mana_cost:
            return (
                False,
                f"Nicht genug Mana! '{spell.name}' kostet {spell.mana_cost} MP, du hast nur {player.magic} MP.",
                0,
                0,
            )

        # Wenn kein Ziel angegeben, Angriffs-Zauber nicht möglich
        if spell.effect_type == "damage" and not target_id:
            return (
                False,
                f"Du musst ein Ziel für '{spell.name}' angeben: cast {spell_name} <npc_id>",
                0,
                0,
            )

        async with self._lock:
            # Verbrauche Mana
            player.magic -= spell.mana_cost

            if spell.effect_type == "damage":
                # Finde Ziel-NPC
                npc = player.current_room.get_npc(target_id)
                if not npc:
                    return False, f"NPC '{target_id}' nicht gefunden.", 0, 0

                if not npc.is_alive():
                    return False, f"{npc.name} ist bereits tot.", 0, 0

                # Füge Schaden zu
                remaining_health = await npc.take_damage(spell.damage)

                message = ""
                # Entferne toten NPC
                if not npc.is_alive():
                    player.current_room.npcs.remove(npc)
                    await self._broadcast_event(
                        "NPC_DIED",
                        f"{player.name} hat {npc.name} mit '{spell.name}' besiegt!",
                        player.current_room.room_id,
                    )
                    message = f"Du wirkst '{spell.name}'! {npc.name} erleidet {spell.damage} Schaden und wurde besiegt!"
                else:
                    await self._broadcast_event(
                        "SPELL_CAST",
                        f"{player.name} wirkt '{spell.name}' auf {npc.name}!",
                        player.current_room.room_id,
                    )
                    message = f"Du wirkst '{spell.name}'! {npc.name} erleidet {spell.damage} Schaden. Verbleibende HP: {remaining_health}"

                    # NPC Gegenzauber
                    if npc.is_alive() and npc.spell_cast_probability > 0:
                        # Prüfe ob NPC zurückzaubert
                        if random.random() < npc.spell_cast_probability:
                            spells = npc.spellbook.list_spells()
                            if spells and npc.magic >= min(s.mana_cost for s in spells):
                                # Wähle zufälligen Zauber, den sich der NPC leisten kann
                                affordable_spells = [
                                    s for s in spells if s.mana_cost <= npc.magic
                                ]
                                if affordable_spells:
                                    counter_spell = random.choice(affordable_spells)
                                    npc.magic -= counter_spell.mana_cost

                                    # Füge Schaden zum Spieler hinzu
                                    player_damage = await player.take_damage(
                                        counter_spell.damage
                                    )

                                    await self._broadcast_event(
                                        "SPELL_CAST",
                                        f"{npc.name} wirkt '{counter_spell.name}' auf {player.name}!",
                                        player.current_room.room_id,
                                    )

                                    message += f"\n💥 {npc.name} kontert mit '{counter_spell.name}'! Du erleidest {counter_spell.damage} Schaden. Verbleibende HP: {player.health}"

                return True, message, spell.damage, remaining_health

            return False, "Unbekannter Zaubertyp.", 0, 0

    async def list_spellbook(self, player_id: str) -> tuple[bool, List[Spell]]:
        """Gibt Zauberbuch des Spielers zurück"""
        player = await self.get_player(player_id)
        if not player:
            return False, []

        return True, player.spellbook.list_spells()
