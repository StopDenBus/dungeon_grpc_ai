"""
Domain Models für das Multi-User Dungeon
"""

from typing import List, Optional, Dict
import uuid
from enum import Enum
import asyncio


class Direction(Enum):
    """Verfügbare Bewegungsrichtungen"""

    NORTH = "north"
    SOUTH = "south"
    EAST = "east"
    WEST = "west"


class Spell:
    """Repräsentiert einen Zauberspruch"""

    def __init__(
        self,
        name: str,
        description: str,
        mana_cost: int,
        damage: int = 0,
        effect_type: str = "damage",
    ):
        self.name = name
        self.description = description
        self.mana_cost = mana_cost
        self.damage = damage
        self.effect_type = effect_type  # "damage", "heal", "buff", etc.

    def __repr__(self):
        return f"Spell({self.name}, mana={self.mana_cost}, dmg={self.damage})"


class Spellbook:
    """Repräsentiert ein Zauberbuch mit erlernten Zaubersprüchen"""

    def __init__(self):
        self.spells: Dict[str, Spell] = {}  # spell_name -> Spell

    def add_spell(self, spell: Spell) -> bool:
        """Fügt einen Zauberspruch hinzu"""
        if spell.name.lower() in self.spells:
            return False  # Bereits gelernt
        self.spells[spell.name.lower()] = spell
        return True

    def has_spell(self, spell_name: str) -> bool:
        """Prüft ob Zauberspruch vorhanden ist"""
        return spell_name.lower() in self.spells

    def get_spell(self, spell_name: str) -> Optional[Spell]:
        """Gibt Zauberspruch zurück"""
        return self.spells.get(spell_name.lower())

    def list_spells(self) -> List[Spell]:
        """Gibt alle Zaubersprüche zurück"""
        return list(self.spells.values())


class Item:
    """Repräsentiert ein Item im Dungeon.

    Subklassen registrieren sich automatisch in der _registry über __init_subclass__,
    indem sie das Schlüsselwort-Argument `item_type` beim Klassenkopf angeben:

        class Weapon(Item, item_type="weapon"):
            ...

    Dadurch kann load_inventory() den korrekten Typ anhand des gespeicherten
    item_type-Strings rekonstruieren, ohne player_db.py je ändern zu müssen.
    """

    _registry: dict = {}  # item_type-String → Subklasse

    def __init_subclass__(cls, item_type: str = None, **kwargs):
        super().__init_subclass__(**kwargs)
        if item_type:
            Item._registry[item_type] = cls

    def __init__(
        self,
        item_id: str = None,
        name: str = "",
        description: str = "",
        value: int = 0,
        guarded_by: List[str] = None,
        item_type: str = "normal",
        spell_name: str = "",
    ):
        self.item_id = item_id if item_id is not None else str(uuid.uuid4())
        self.name = name
        self.description = description
        self.value = value
        self.guarded_by = (
            guarded_by if guarded_by is not None else []
        )  # Liste von NPC-Namen, die dieses Item bewachen
        self.item_type = item_type  # "normal", "scroll", "spellbook", "weapon", ...
        self.spell_name = spell_name  # Für Zauberspruchrollen

    def to_dict(self) -> dict:
        """Serialisiert das Item in ein Dict für die Datenbank.

        Subklassen erweitern diese Methode und schreiben ihre Extra-Felder
        in den 'extra_data'-Schlüssel:

            def to_dict(self):
                d = super().to_dict()
                d["extra_data"]["damage"] = self.damage
                return d
        """
        return {
            "item_id": self.item_id,
            "name": self.name,
            "description": self.description,
            "value": self.value,
            "item_type": self.item_type,
            "spell_name": self.spell_name,
            "extra_data": {},
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Item":
        """Rekonstruiert ein Item-Objekt aus einem serialisierten Dict.

        Subklassen überschreiben diese Methode, um ihre Extra-Felder aus
        data["extra_data"] zu lesen.
        """
        return cls(
            item_id=data["item_id"],
            name=data["name"],
            description=data["description"],
            value=data["value"],
            item_type=data["item_type"],
            spell_name=data.get("spell_name", ""),
        )

    def to_proto_item(self):
        """Konvertiert zu Proto Item Message"""
        from . import dungeon_pb2

        return dungeon_pb2.Item(
            item_id=self.item_id,
            name=self.name,
            description=self.description,
            value=self.value,
        )


class Weapon(Item, item_type="weapon"):
    """Eine Waffe mit Schadenswert."""

    def __init__(self, damage: int = 0, **kwargs):
        kwargs.setdefault("item_type", "weapon")
        super().__init__(**kwargs)
        self.damage = damage

    def to_dict(self) -> dict:
        d = super().to_dict()
        d["extra_data"]["damage"] = self.damage
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "Weapon":
        extra = data.get("extra_data", {})
        return cls(
            item_id=data["item_id"],
            name=data["name"],
            description=data["description"],
            value=data["value"],
            item_type=data.get("item_type", "weapon"),
            spell_name=data.get("spell_name", ""),
            damage=extra.get("damage", 0),
        )


class Chest:
    """Repräsentiert eine Kiste/Container im Dungeon"""

    def __init__(
        self,
        chest_id: str = None,
        name: str = "",
        description: str = "",
        is_open: bool = False,
        items: List[Item] = None,
        guarded_by: List[str] = None,
    ):
        self.chest_id = chest_id if chest_id is not None else str(uuid.uuid4())
        self.name = name
        self.description = description
        self.is_open = is_open
        self.items = items if items is not None else []
        self.guarded_by = (
            guarded_by if guarded_by is not None else []
        )  # Liste von NPC-Namen, die diese Kiste bewachen

    def open(self) -> tuple[bool, str]:
        """Öffnet die Kiste"""
        if self.is_open:
            return False, f"{self.name} ist bereits geöffnet."
        self.is_open = True
        return True, f"Du öffnest {self.name}."

    def close(self) -> tuple[bool, str]:
        """Schließt die Kiste"""
        if not self.is_open:
            return False, f"{self.name} ist bereits geschlossen."
        self.is_open = False
        return True, f"Du schließt {self.name}."

    def add_item(self, item: Item) -> tuple[bool, str]:
        """Legt Item in die Kiste"""
        if not self.is_open:
            return False, f"{self.name} ist geschlossen. Du musst sie erst öffnen."
        self.items.append(item)
        return True, f"Du legst {item.name} in {self.name}."

    def remove_item_by_name(self, item_name: str, index: int = 1) -> Optional[Item]:
        """Entfernt Item aus Kiste nach Namen und Index"""
        if not self.is_open:
            return None
        matching_indices = [
            i
            for i, item in enumerate(self.items)
            if item.name.lower() == item_name.lower()
        ]
        if 0 < index <= len(matching_indices):
            actual_index = matching_indices[index - 1]
            return self.items.pop(actual_index)
        return None

    def get_status(self) -> str:
        """Gibt Status-String zurück"""
        status = "geöffnet" if self.is_open else "geschlossen"
        item_count = len(self.items)
        return f"{self.name} ({status}, {item_count} Items)"

    def to_proto_chest(self):
        """Konvertiert zu Proto Chest Message"""
        from . import dungeon_pb2

        return dungeon_pb2.Chest(
            chest_id=self.chest_id,
            name=self.name,
            description=self.description,
            is_open=self.is_open,
            items=[item.to_proto_item() for item in self.items],
        )


class LivingEntity:
    """Basisklasse für lebende Entitäten mit Heartbeat-Mechanismus"""

    def __init__(
        self,
        name: str = "",
        description: str = "",
        health: int = 100,
        max_health: int = 100,
        magic: int = 50,
        max_magic: int = 100,
    ):
        self.name = name
        self.description = description
        self.health = health
        self.max_health = max_health
        self.magic = magic
        self.max_magic = max_magic
        self.spellbook = Spellbook()
        self._heartbeat_task: Optional[asyncio.Task] = None
        self._stop_heartbeat: bool = False
        self.start_heartbeat()

    async def heartbeat(self) -> None:
        """Heartbeat-Schleife: Erhöht Health und Magic um 1 alle 2 Sekunden"""
        while not self._stop_heartbeat:
            await asyncio.sleep(2)
            if self.health < self.max_health:
                self.health = min(self.max_health, self.health + 1)
            if self.magic < self.max_magic:
                self.magic = min(self.max_magic, self.magic + 1)

    def start_heartbeat(self) -> None:
        """Startet den Heartbeat-Task"""
        if self._heartbeat_task is None or self._heartbeat_task.done():
            self._stop_heartbeat = False
            try:
                self._heartbeat_task = asyncio.create_task(self.heartbeat())
            except RuntimeError:
                # Kein Event Loop vorhanden - Heartbeat wird später manuell gestartet
                pass

    def stop_heartbeat(self) -> None:
        """Stoppt den Heartbeat-Task"""
        self._stop_heartbeat = True
        if self._heartbeat_task and not self._heartbeat_task.done():
            self._heartbeat_task.cancel()

    async def take_damage(self, damage: int) -> int:
        """Reduziert Health"""
        self.health = max(0, self.health - damage)
        return self.health

    def is_alive(self) -> bool:
        """Prüft ob Entität noch lebt"""
        return self.health > 0


class NPC(LivingEntity):
    """Repräsentiert einen Non-Player Character"""

    def __init__(
        self,
        npc_id: str = None,
        name: str = "",
        description: str = "",
        health: int = 100,
        max_health: int = 100,
        magic: int = 50,
        max_magic: int = 100,
        is_hostile: bool = False,
        dialogue: str = "",
        spell_cast_probability: float = 0.0,
    ):
        super().__init__(
            name=name,
            description=description,
            health=health,
            max_health=max_health,
            magic=magic,
            max_magic=max_magic,
        )
        self.npc_id = npc_id if npc_id is not None else str(uuid.uuid4())
        self.is_hostile = is_hostile
        self.dialogue = dialogue
        self.spell_cast_probability = spell_cast_probability  # Wahrscheinlichkeit 0.0-1.0, dass NPC einen Zauber wirkt

    async def talk(self) -> str:
        """NPC Dialogue"""
        return self.dialogue

    def to_proto_npc(self):
        """Konvertiert zu Proto NPC Message"""
        from . import dungeon_pb2

        return dungeon_pb2.NPC(
            npc_id=self.npc_id,
            name=self.name,
            description=self.description,
            health=self.health,
            magic=self.magic,
            is_hostile=self.is_hostile,
            dialogue=self.dialogue,
        )


class Room:
    """Repräsentiert einen Raum im Dungeon"""

    def __init__(
        self,
        room_id: str = None,
        name: str = "",
        description: str = "",
        exits: dict[Direction, Optional["Room"]] = None,
        items: List[Item] = None,
        chests: List[Chest] = None,
        npcs: List[NPC] = None,
        players: List["Player"] = None,
        guarded_by: List[str] = None,
    ):
        self.room_id = room_id if room_id is not None else str(uuid.uuid4())
        self.name = name
        self.description = description
        self.exits = exits if exits is not None else {}
        self.items = items if items is not None else []
        self.chests = chests if chests is not None else []
        self.npcs = npcs if npcs is not None else []
        self.players = players if players is not None else []
        self.guarded_by = guarded_by if guarded_by is not None else []

    def add_exit(self, direction: Direction, room: "Room") -> None:
        """Fügt einen Ausgang hinzu"""
        self.exits[direction] = room

    def get_exit(self, direction: Direction) -> Optional["Room"]:
        """Gibt Raum in angegebener Richtung zurück"""
        return self.exits.get(direction)

    def add_item(self, item: Item) -> None:
        """Fügt Item zum Raum hinzu"""
        self.items.append(item)

    def remove_item(self, item_id: str) -> Optional[Item]:
        """Entfernt Item aus Raum"""
        for i, item in enumerate(self.items):
            if item.item_id == item_id:
                return self.items.pop(i)
        return None

    def get_item(self, item_id: str) -> Optional[Item]:
        """Findet Item im Raum"""
        return next((item for item in self.items if item.item_id == item_id), None)

    def get_item_by_name(self, item_name: str, index: int = 1) -> Optional[Item]:
        """Findet Item im Raum nach Namen und optionalem Index (1-basiert)"""
        matching_items = [
            item for item in self.items if item.name.lower() == item_name.lower()
        ]
        if 0 < index <= len(matching_items):
            return matching_items[index - 1]
        return None

    def remove_item_by_name(self, item_name: str, index: int = 1) -> Optional[Item]:
        """Entfernt Item aus Raum nach Namen und optionalem Index (1-basiert)"""
        matching_indices = [
            i
            for i, item in enumerate(self.items)
            if item.name.lower() == item_name.lower()
        ]
        if 0 < index <= len(matching_indices):
            actual_index = matching_indices[index - 1]
            return self.items.pop(actual_index)
        return None

    def add_npc(self, npc: NPC) -> None:
        """Fügt NPC zum Raum hinzu"""
        self.npcs.append(npc)

    def get_npc(self, npc_id: str) -> Optional[NPC]:
        """Findet NPC im Raum nach ID oder Name"""
        # Versuche zuerst nach ID
        npc = next((npc for npc in self.npcs if npc.npc_id == npc_id), None)
        if npc:
            return npc
        # Falls nicht gefunden, versuche nach Name (case-insensitive)
        return next(
            (npc for npc in self.npcs if npc.name.lower() == npc_id.lower()), None
        )

    def add_chest(self, chest: Chest) -> None:
        """Fügt Kiste zum Raum hinzu"""
        self.chests.append(chest)

    def get_chest_by_name(self, chest_name: str, index: int = 1) -> Optional[Chest]:
        """Findet Kiste im Raum nach Namen und Index"""
        matching_chests = [
            chest for chest in self.chests if chest.name.lower() == chest_name.lower()
        ]
        if 0 < index <= len(matching_chests):
            return matching_chests[index - 1]
        return None

    def add_player(self, player: "Player") -> None:
        """Fügt Spieler zum Raum hinzu"""
        if player not in self.players:
            self.players.append(player)

    def remove_player(self, player: "Player") -> None:
        """Entfernt Spieler aus Raum"""
        if player in self.players:
            self.players.remove(player)

    def get_available_exits(self) -> List[str]:
        """Liste verfügbarer Ausgänge"""
        return [
            direction.value
            for direction, room in self.exits.items()
            if room is not None
        ]

    def to_proto_room(self):
        """Konvertiert zu Proto RoomInfo Message"""
        from . import dungeon_pb2

        return dungeon_pb2.RoomInfo(
            room_id=self.room_id,
            name=self.name,
            description=self.description,
            exits=self.get_available_exits(),
            items=[item.to_proto_item() for item in self.items],
            chests=[chest.to_proto_chest() for chest in self.chests],
            npcs=[npc.to_proto_npc() for npc in self.npcs],
            players=[player.name for player in self.players],
        )


class Player(LivingEntity):
    """Repräsentiert einen Spieler"""

    def __init__(
        self,
        player_id: str = None,
        name: str = "",
        description: str = "",
        health: int = 50,
        max_health: int = 100,
        magic: int = 30,
        max_magic: int = 100,
        current_room: Optional[Room] = None,
        inventory: List[Item] = None,
    ):
        super().__init__(
            name=name,
            description=description,
            health=health,
            max_health=max_health,
            magic=magic,
            max_magic=max_magic,
        )
        self.player_id = player_id if player_id is not None else str(uuid.uuid4())
        self.current_room = current_room
        self.inventory = inventory if inventory is not None else []

    async def move_to(self, direction: Direction) -> Optional[Room]:
        """Bewegt Spieler in angegebene Richtung"""
        if self.current_room is None:
            return None

        new_room = self.current_room.get_exit(direction)
        if new_room:
            # Entfernt Spieler aus altem Raum
            self.current_room.remove_player(self)
            # Fügt Spieler zu neuem Raum hinzu
            new_room.add_player(self)
            self.current_room = new_room
            return new_room
        return None

    async def take_item(self, item_name: str, index: int = 1) -> Optional[Item]:
        """Nimmt Item aus aktuellem Raum auf (nach Namen und optionalem Index)"""
        if self.current_room is None:
            return None

        item = self.current_room.remove_item_by_name(item_name, index)
        if item:
            self.inventory.append(item)
        return item

    async def drop_item(self, item_name: str, index: int = 1) -> Optional[Item]:
        """Legt Item im aktuellen Raum ab (nach Namen und optionalem Index)"""
        if self.current_room is None:
            return None

        matching_indices = [
            i
            for i, item in enumerate(self.inventory)
            if item.name.lower() == item_name.lower()
        ]
        if 0 < index <= len(matching_indices):
            actual_index = matching_indices[index - 1]
            dropped_item = self.inventory.pop(actual_index)
            self.current_room.add_item(dropped_item)
            return dropped_item
        return None

    async def attack_npc(self, npc_id: str) -> tuple[bool, int, int]:
        """Greift NPC an. Returns (success, damage_dealt, npc_health)"""
        if self.current_room is None:
            return False, 0, 0

        npc = self.current_room.get_npc(npc_id)
        if npc and npc.is_alive():
            damage = 20  # Fixer Damage für Einfachheit
            remaining_health = await npc.take_damage(damage)

            # Entfernt toten NPC
            if not npc.is_alive():
                self.current_room.npcs.remove(npc)

            return True, damage, remaining_health
        return False, 0, 0

    def to_proto_player(self):
        """Konvertiert zu Proto PlayerInfo Message"""
        from . import dungeon_pb2

        return dungeon_pb2.PlayerInfo(
            player_id=self.player_id,
            name=self.name,
            current_room_id=self.current_room.room_id if self.current_room else "",
            health=self.health,
            magic=self.magic,
            inventory=[item.to_proto_item() for item in self.inventory],
        )
