"""
gRPC Client für das Multi-User Dungeon
"""
import asyncio
import logging
from typing import Optional
import grpc
from . import dungeon_pb2
from . import dungeon_pb2_grpc

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class DungeonClient:
    """
    Client für die Kommunikation mit dem Dungeon Server
    """

    def __init__(self, server_address: str = "localhost:50051"):
        self.server_address = server_address
        self.channel: Optional[grpc.aio.Channel] = None
        self.stub: Optional[dungeon_pb2_grpc.DungeonServiceStub] = None
        self.player_id: Optional[str] = None
        self.player_name: Optional[str] = None
        self.event_task: Optional[asyncio.Task] = None

    async def connect(self):
        """Verbindet mit dem Server"""
        self.channel = grpc.aio.insecure_channel(self.server_address)
        self.stub = dungeon_pb2_grpc.DungeonServiceStub(self.channel)
        logger.info(f"Verbunden mit Server: {self.server_address}")

    async def disconnect(self):
        """Trennt Verbindung zum Server"""
        # Melde Spieler ordentlich ab
        if self.stub and self.player_id:
            try:
                request = dungeon_pb2.UnregisterPlayerRequest(player_id=self.player_id)
                response = await self.stub.UnregisterPlayer(request)
                if response.success:
                    logger.info(response.message)
            except Exception as e:
                logger.error(f"Fehler beim Abmelden: {e}")

        if self.event_task:
            self.event_task.cancel()
            try:
                await self.event_task
            except asyncio.CancelledError:
                pass

        if self.channel:
            await self.channel.close()
            logger.info("Verbindung getrennt")

    async def register(self, player_name: str) -> bool:
        """Registriert Spieler beim Server"""
        if not self.stub:
            logger.error("Nicht mit Server verbunden")
            return False

        request = dungeon_pb2.RegisterPlayerRequest(player_name=player_name)
        response = await self.stub.RegisterPlayer(request)

        if response.success:
            self.player_id = response.player_id
            self.player_name = player_name
            logger.info(response.message)

            # Starte Event Stream
            self.event_task = asyncio.create_task(self._stream_events())
            return True
        else:
            logger.error(response.message)
            return False

    async def move(self, direction: str) -> bool:
        """Bewegt Spieler in eine Richtung"""
        if not self.stub or not self.player_id:
            logger.error("Nicht eingeloggt")
            return False

        request = dungeon_pb2.MovePlayerRequest(
            player_id=self.player_id,
            direction=direction
        )
        response = await self.stub.MovePlayer(request)

        print(f"\n{response.message}")
        if response.success and response.HasField("new_room"):
            self._print_room(response.new_room)

        return response.success

    async def look_around(self):
        """Schaut sich im aktuellen Raum um"""
        if not self.stub or not self.player_id:
            logger.error("Nicht eingeloggt")
            return

        request = dungeon_pb2.LookAroundRequest(player_id=self.player_id)
        response = await self.stub.LookAround(request)

        if response.HasField("room"):
            self._print_room(response.room)

    async def take_item(self, item_id: str):
        """Nimmt Item auf"""
        if not self.stub or not self.player_id:
            logger.error("Nicht eingeloggt")
            return

        request = dungeon_pb2.TakeItemRequest(
            player_id=self.player_id,
            item_id=item_id
        )
        response = await self.stub.TakeItem(request)
        print(f"\n{response.message}")

    async def drop_item(self, item_id: str):
        """Legt Item ab"""
        if not self.stub or not self.player_id:
            logger.error("Nicht eingeloggt")
            return

        request = dungeon_pb2.DropItemRequest(
            player_id=self.player_id,
            item_id=item_id
        )
        response = await self.stub.DropItem(request)
        print(f"\n{response.message}")

    async def talk_to_npc(self, npc_id: str):
        """Spricht mit NPC"""
        if not self.stub or not self.player_id:
            logger.error("Nicht eingeloggt")
            return

        request = dungeon_pb2.TalkToNPCRequest(
            player_id=self.player_id,
            npc_id=npc_id
        )
        response = await self.stub.TalkToNPC(request)

        print(f"\n{response.message}")
        if response.success:
            print(f"'{response.npc_response}'")

    async def attack_npc(self, npc_id: str):
        """Greift NPC an"""
        if not self.stub or not self.player_id:
            logger.error("Nicht eingeloggt")
            return

        request = dungeon_pb2.AttackNPCRequest(
            player_id=self.player_id,
            npc_id=npc_id
        )
        response = await self.stub.AttackNPC(request)

        print(f"\n{response.message}")
        if response.success:
            print(f"Schaden: {response.damage_dealt}, Verbleibende Health: {response.npc_health_remaining}")

    async def get_player_info(self):
        """Zeigt Spieler-Information"""
        if not self.stub or not self.player_id:
            logger.error("Nicht eingeloggt")
            return

        request = dungeon_pb2.GetPlayerInfoRequest(player_id=self.player_id)
        response = await self.stub.GetPlayerInfo(request)

        print(f"\n=== Spieler Info ===")
        print(f"Name: {response.name}")
        print(f"Health: {response.health}")
        print(f"Inventar ({len(response.inventory)} Items):")
        for item in response.inventory:
            print(f"  - {item.name} (ID: {item.item_id}): {item.description} [Wert: {item.value}]")

    async def send_direct_message(self, recipient_name: str, message: str):
        """Sendet direkte Nachricht an Spieler"""
        if not self.stub or not self.player_id:
            logger.error("Nicht eingeloggt")
            return

        request = dungeon_pb2.SendDirectMessageRequest(
            sender_id=self.player_id,
            recipient_name=recipient_name,
            message=message
        )
        response = await self.stub.SendDirectMessage(request)
        print(f"\n{response.message}")

    async def send_room_message(self, message: str):
        """Sendet Nachricht an alle im Raum"""
        if not self.stub or not self.player_id:
            logger.error("Nicht eingeloggt")
            return

        request = dungeon_pb2.SendRoomMessageRequest(
            sender_id=self.player_id,
            message=message
        )
        response = await self.stub.SendRoomMessage(request)
        if not response.success:
            print(f"\n{response.message}")

    async def send_broadcast_message(self, message: str):
        """Sendet Broadcast an alle Spieler"""
        if not self.stub or not self.player_id:
            logger.error("Nicht eingeloggt")
            return

        request = dungeon_pb2.SendBroadcastMessageRequest(
            sender_id=self.player_id,
            message=message
        )
        response = await self.stub.SendBroadcastMessage(request)
        if not response.success:
            print(f"\n{response.message}")

    async def get_online_players(self):
        """Zeigt Liste aller Online-Spieler"""
        if not self.stub or not self.player_id:
            logger.error("Nicht eingeloggt")
            return

        request = dungeon_pb2.GetOnlinePlayersRequest(player_id=self.player_id)
        response = await self.stub.GetOnlinePlayers(request)

        print(f"\n=== Online Spieler ({len(response.players)}) ===")
        for player in response.players:
            print(f"  • {player.name} - {player.room_name}")

    def _print_room(self, room: dungeon_pb2.RoomInfo):
        """Gibt Raum-Information formatiert aus"""
        print(f"\n{'='*60}")
        print(f"📍 {room.name}")
        print(f"{'='*60}")
        print(f"{room.description}")
        print()

        if room.exits:
            print(f"🚪 Ausgänge: {', '.join(room.exits)}")

        if room.items:
            print(f"\n💎 Items im Raum:")
            for item in room.items:
                print(f"  - {item.name} (ID: {item.item_id}): {item.description}")

        if room.npcs:
            print(f"\n👤 NPCs:")
            for npc in room.npcs:
                hostile = "⚔️ FEINDLICH" if npc.is_hostile else "🤝 Friedlich"
                print(f"  - {npc.name} (ID: {npc.npc_id}) [{hostile}]")
                print(f"    {npc.description} (Health: {npc.health})")

        if room.players:
            print(f"\n👥 Andere Spieler: {', '.join(room.players)}")

        print(f"{'='*60}\n")

    async def _stream_events(self):
        """Empfängt und verarbeitet Game Events"""
        if not self.stub or not self.player_id:
            return

        request = dungeon_pb2.StreamEventsRequest(player_id=self.player_id)

        try:
            async for event in self.stub.StreamEvents(request):
                event_type = dungeon_pb2.GameEvent.EventType.Name(event.event_type)

                # Formatiere Nachrichten basierend auf Typ
                if event_type in ["DIRECT_MESSAGE", "ROOM_MESSAGE", "BROADCAST_MESSAGE"]:
                    # Nachrichten mit speziellem Präfix
                    if event_type == "DIRECT_MESSAGE":
                        print(f"\n💬 {event.message}")
                    elif event_type == "ROOM_MESSAGE":
                        print(f"\n💭 {event.message}")
                    elif event_type == "BROADCAST_MESSAGE":
                        print(f"\n📢 {event.message}")
                else:
                    # Standard Events
                    print(f"\n🔔 EVENT: {event.message}")
        except asyncio.CancelledError:
            logger.info("Event Stream beendet")
        except Exception as e:
            logger.error(f"Event Stream Fehler: {e}")


async def interactive_client():
    """Interaktiver Client mit Kommandozeile"""
    client = DungeonClient()

    print("=== Multi-User Dungeon Client ===")
    print("Verbinde mit Server...")

    try:
        await client.connect()
    except Exception as e:
        print(f"Fehler beim Verbinden: {e}")
        return

    player_name = input("Gib deinen Spielernamen ein: ").strip()
    if not player_name:
        print("Ungültiger Name")
        await client.disconnect()
        return

    if not await client.register(player_name):
        print("Registrierung fehlgeschlagen")
        await client.disconnect()
        return

    # Zeige aktuellen Raum
    await client.look_around()

    print("\n=== Kommandos ===")
    print("move <direction>    - Bewege dich (north, south, east, west)")
    print("look                - Schau dich um")
    print("take <item_id>      - Nimm Item auf")
    print("drop <item_id>      - Lege Item ab")
    print("talk <npc_id>       - Sprich mit NPC")
    print("attack <npc_id>     - Greife NPC an")
    print("info                - Zeige Spieler-Info")
    print("msg <name> <text>   - Direkte Nachricht an Spieler")
    print("say <text>          - Nachricht an alle im Raum")
    print("shout <text>        - Broadcast an alle Spieler")
    print("who                 - Zeige Online-Spieler")
    print("help                - Zeige Kommandos")
    print("quit                - Beende Client")
    print()
    print("attack <npc_id>     - Greife NPC an")
    print("info                - Zeige Spieler-Info")
    print("help                - Zeige Kommandos")
    print("quit                - Beende Client")
    print()

    try:
        while True:
            try:
                command = await asyncio.get_event_loop().run_in_executor(
                    None, input, f"\n[{player_name}]> "
                )
                command = command.strip()

                if not command:
                    continue

                parts = command.split(maxsplit=1)
                cmd = parts[0].lower()
                arg = parts[1] if len(parts) > 1 else None

                if cmd == "quit":
                    break
                elif cmd == "move" and arg:
                    await client.move(arg)
                elif cmd == "look":
                    await client.look_around()
                elif cmd == "take" and arg:
                    await client.take_item(arg)
                elif cmd == "drop" and arg:
                    await client.drop_item(arg)
                elif cmd == "talk" and arg:
                    await client.talk_to_npc(arg)
                elif cmd == "attack" and arg:
                    await client.attack_npc(arg)
                elif cmd == "info":
                    await client.get_player_info()
                elif cmd == "msg" and arg:
                    # msg <name> <text>
                    msg_parts = arg.split(maxsplit=1)
                    if len(msg_parts) == 2:
                        await client.send_direct_message(msg_parts[0], msg_parts[1])
                    else:
                        print("Verwendung: msg <spielername> <nachricht>")
                elif cmd == "say" and arg:
                    await client.send_room_message(arg)
                elif cmd == "shout" and arg:
                    await client.send_broadcast_message(arg)
                elif cmd == "who":
                    await client.get_online_players()
                elif cmd == "help":
                    print("\n=== Kommandos ===")
                    print("move <direction>    - Bewege dich (north, south, east, west)")
                    print("look                - Schau dich um")
                    print("take <item_id>      - Nimm Item auf")
                    print("drop <item_id>      - Lege Item ab")
                    print("talk <npc_id>       - Sprich mit NPC")
                    print("attack <npc_id>     - Greife NPC an")
                    print("info                - Zeige Spieler-Info")
                    print("msg <name> <text>   - Direkte Nachricht an Spieler")
                    print("say <text>          - Nachricht an alle im Raum")
                    print("shout <text>        - Broadcast an alle Spieler")
                    print("who                 - Zeige Online-Spieler")
                    print("help                - Zeige Kommandos")
                    print("quit                - Beende Client")
                else:
                    print("Unbekanntes Kommando. Nutze 'help' für Hilfe.")

            except EOFError:
                break
            except KeyboardInterrupt:
                break
    finally:
        print("\nTschüss!")
        await client.disconnect()


def main():
    """Entry point für den Client"""
    asyncio.run(interactive_client())


if __name__ == "__main__":
    main()
