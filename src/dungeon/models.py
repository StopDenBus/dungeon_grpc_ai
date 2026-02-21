"""
Domain Models für das Multi-User Dungeon
"""
from dataclasses import dataclass, field
from typing import List, Optional
import uuid
from enum import Enum


class Direction(Enum):
    """Verfügbare Bewegungsrichtungen"""
    NORTH = "north"
    SOUTH = "south"
    EAST = "east"
    WEST = "west"


@dataclass
class Item:
    """Repräsentiert ein Item im Dungeon"""
    item_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    name: str = ""
    description: str = ""
    value: int = 0

    def to_proto_item(self):
        """Konvertiert zu Proto Item Message"""
        from . import dungeon_pb2
        return dungeon_pb2.Item(
            item_id=self.item_id,
            name=self.name,
            description=self.description,
            value=self.value
        )


@dataclass
class NPC:
    """Repräsentiert einen Non-Player Character"""
    npc_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    name: str = ""
    description: str = ""
    health: int = 100
    is_hostile: bool = False
    dialogue: str = ""

    async def talk(self) -> str:
        """NPC Dialogue"""
        return self.dialogue

    async def take_damage(self, damage: int) -> int:
        """Reduziert NPC Health"""
        self.health = max(0, self.health - damage)
        return self.health

    def is_alive(self) -> bool:
        """Prüft ob NPC noch lebt"""
        return self.health > 0

    def to_proto_npc(self):
        """Konvertiert zu Proto NPC Message"""
        from . import dungeon_pb2
        return dungeon_pb2.NPC(
            npc_id=self.npc_id,
            name=self.name,
            description=self.description,
            health=self.health,
            is_hostile=self.is_hostile,
            dialogue=self.dialogue
        )


@dataclass
class Room:
    """Repräsentiert einen Raum im Dungeon"""
    room_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    name: str = ""
    description: str = ""
    exits: dict[Direction, Optional['Room']] = field(default_factory=dict)
    items: List[Item] = field(default_factory=list)
    npcs: List[NPC] = field(default_factory=list)
    players: List['Player'] = field(default_factory=list)

    def add_exit(self, direction: Direction, room: 'Room') -> None:
        """Fügt einen Ausgang hinzu"""
        self.exits[direction] = room

    def get_exit(self, direction: Direction) -> Optional['Room']:
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

    def add_npc(self, npc: NPC) -> None:
        """Fügt NPC zum Raum hinzu"""
        self.npcs.append(npc)

    def get_npc(self, npc_id: str) -> Optional[NPC]:
        """Findet NPC im Raum"""
        return next((npc for npc in self.npcs if npc.npc_id == npc_id), None)

    def add_player(self, player: 'Player') -> None:
        """Fügt Spieler zum Raum hinzu"""
        if player not in self.players:
            self.players.append(player)

    def remove_player(self, player: 'Player') -> None:
        """Entfernt Spieler aus Raum"""
        if player in self.players:
            self.players.remove(player)

    def get_available_exits(self) -> List[str]:
        """Liste verfügbarer Ausgänge"""
        return [direction.value for direction, room in self.exits.items() if room is not None]

    def to_proto_room(self):
        """Konvertiert zu Proto RoomInfo Message"""
        from . import dungeon_pb2
        return dungeon_pb2.RoomInfo(
            room_id=self.room_id,
            name=self.name,
            description=self.description,
            exits=self.get_available_exits(),
            items=[item.to_proto_item() for item in self.items],
            npcs=[npc.to_proto_npc() for npc in self.npcs],
            players=[player.name for player in self.players]
        )


@dataclass
class Player:
    """Repräsentiert einen Spieler"""
    player_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    name: str = ""
    current_room: Optional[Room] = None
    health: int = 100
    inventory: List[Item] = field(default_factory=list)

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

    async def take_item(self, item_id: str) -> Optional[Item]:
        """Nimmt Item aus aktuellem Raum auf"""
        if self.current_room is None:
            return None

        item = self.current_room.remove_item(item_id)
        if item:
            self.inventory.append(item)
        return item

    async def drop_item(self, item_id: str) -> Optional[Item]:
        """Legt Item im aktuellen Raum ab"""
        if self.current_room is None:
            return None

        for i, item in enumerate(self.inventory):
            if item.item_id == item_id:
                dropped_item = self.inventory.pop(i)
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
            inventory=[item.to_proto_item() for item in self.inventory]
        )
