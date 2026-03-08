"""
gRPC Client für das Multi-User Dungeon
"""

import asyncio
import logging
from typing import Optional
from datetime import datetime
from pathlib import Path
import grpc.aio
from prompt_toolkit import Application
from prompt_toolkit.buffer import Buffer
from prompt_toolkit.clipboard import ClipboardData
from prompt_toolkit.filters import Condition
from prompt_toolkit.history import InMemoryHistory
from prompt_toolkit.key_binding import KeyBindings, merge_key_bindings
from prompt_toolkit.key_binding.bindings.focus import focus_next, focus_previous
from prompt_toolkit.layout.containers import HSplit, VSplit, Window
from prompt_toolkit.layout.controls import BufferControl, FormattedTextControl
from prompt_toolkit.layout.layout import Layout
from prompt_toolkit.styles import Style
from prompt_toolkit.widgets import TextArea
from . import dungeon_pb2
from . import dungeon_pb2_grpc

# Logging Setup - schreibt in Datei
log_dir = Path.home() / ".dungeon" / "logs"
log_dir.mkdir(parents=True, exist_ok=True)
log_file = log_dir / f"client_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler(log_file),
        # logging.StreamHandler()  # Auch in Konsole für kritische Fehler
    ],
)
logger = logging.getLogger(__name__)
logger.info(f"Client logging to: {log_file}")

# Style für die UI
ui_style = Style.from_dict(
    {
        "output-field": "bg:#1e1e1e #cccccc",
        "input-field": "bg:#252525 #00ff00",
        "line": "#444444",
        "info-bar": "bg:#005f87 #ffffff bold",
    }
)


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
        self.stop_events = asyncio.Event()
        self.output_callback = None  # Callback für UI-Output

    def set_output_callback(self, callback):
        """Setzt Callback für Output-Updates"""
        self.output_callback = callback

    def _output(self, text: str):
        """Sendet Output an Callback oder stdout"""
        if self.output_callback:
            self.output_callback(text)
        else:
            print(text)

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

        # Stoppe Event Task
        if self.event_task and not self.event_task.done():
            self.stop_events.set()
            try:
                await asyncio.wait_for(self.event_task, timeout=2.0)
            except asyncio.TimeoutError:
                self.event_task.cancel()

        if self.channel:
            await self.channel.close()
            logger.info("Verbindung getrennt")

    async def register(self, player_name: str, password: str) -> bool:
        """Registriert Spieler beim Server oder meldet bestehenden an."""
        if not self.stub:
            logger.error("Nicht mit Server verbunden")
            return False

        request = dungeon_pb2.RegisterPlayerRequest(
            player_name=player_name, password=password
        )
        response = await self.stub.RegisterPlayer(request)

        if response.success:
            self.player_id = response.player_id
            self.player_name = player_name
            logger.info(response.message)

            # Starte Event Stream als asyncio Task
            self.event_task = asyncio.create_task(self._stream_events())
            return True
        else:
            logger.error(response.message)
            print(f"✗ {response.message}")
            return False

    async def move(self, direction: str) -> bool:
        """Bewegt Spieler in eine Richtung"""
        if not self.stub or not self.player_id:
            logger.error("Nicht eingeloggt")
            return False

        request = dungeon_pb2.MovePlayerRequest(
            player_id=self.player_id, direction=direction
        )
        response = await self.stub.MovePlayer(request)

        self._output(f"\n{response.message}")
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

        request = dungeon_pb2.TakeItemRequest(player_id=self.player_id, item_id=item_id)
        response = await self.stub.TakeItem(request)
        self._output(f"\n{response.message}")

    async def drop_item(self, item_id: str):
        """Legt Item ab"""
        if not self.stub or not self.player_id:
            logger.error("Nicht eingeloggt")
            return

        request = dungeon_pb2.DropItemRequest(player_id=self.player_id, item_id=item_id)
        response = await self.stub.DropItem(request)
        self._output(f"\n{response.message}")

    async def talk_to_npc(self, npc_id: str):
        """Spricht mit NPC"""
        if not self.stub or not self.player_id:
            logger.error("Nicht eingeloggt")
            return

        request = dungeon_pb2.TalkToNPCRequest(player_id=self.player_id, npc_id=npc_id)
        response = await self.stub.TalkToNPC(request)

        self._output(f"\n{response.message}")
        if response.success:
            self._output(f"'{response.npc_response}'")

    async def attack_npc(self, npc_id: str):
        """Greift NPC an"""
        if not self.stub or not self.player_id:
            logger.error("Nicht eingeloggt")
            return

        request = dungeon_pb2.AttackNPCRequest(player_id=self.player_id, npc_id=npc_id)
        response = await self.stub.AttackNPC(request)

        self._output(f"\n{response.message}")
        if response.success:
            self._output(
                f"Schaden: {response.damage_dealt}, Verbleibende Health: {response.npc_health_remaining}"
            )

    async def get_player_info(self):
        """Zeigt Spieler-Information"""
        if not self.stub or not self.player_id:
            logger.error("Nicht eingeloggt")
            return

        request = dungeon_pb2.GetPlayerInfoRequest(player_id=self.player_id)
        response = await self.stub.GetPlayerInfo(request)

        self._output(f"\n=== Spieler Info ===")
        self._output(f"Name: {response.name}")
        self._output(f"Health: {response.health}")
        self._output(f"Magic: {response.magic}")
        self._output(f"Inventar ({len(response.inventory)} Items):")
        for item in response.inventory:
            self._output(
                f"  - {item.name} (ID: {item.item_id}): {item.description} [Wert: {item.value}]"
            )

    async def read_scroll(self, item_name: str):
        """Liest eine Zauberspruchrolle"""
        if not self.stub or not self.player_id:
            logger.error("Nicht eingeloggt")
            return

        request = dungeon_pb2.ReadScrollRequest(
            player_id=self.player_id, item_name=item_name
        )
        response = await self.stub.ReadScroll(request)
        self._output(f"\n{response.message}")

    async def cast_spell(self, spell_name: str, target_id: str = ""):
        """Zaubert einen Spruch"""
        if not self.stub or not self.player_id:
            logger.error("Nicht eingeloggt")
            return

        request = dungeon_pb2.CastSpellRequest(
            player_id=self.player_id, spell_name=spell_name, target_id=target_id
        )
        response = await self.stub.CastSpell(request)
        self._output(f"\n{response.message}")

    async def list_spellbook(self):
        """Zeigt Zauberbuch"""
        if not self.stub or not self.player_id:
            logger.error("Nicht eingeloggt")
            return

        request = dungeon_pb2.ListSpellbookRequest(player_id=self.player_id)
        response = await self.stub.ListSpellbook(request)

        if not response.spells:
            self._output(
                "\nDein Zauberbuch ist leer. Finde Zauberspruchrollen um Zauber zu lernen!"
            )
            return

        self._output("\n=== 📖 Zauberbuch ===")
        for spell in response.spells:
            self._output(f"\n✨ {spell.name}")
            self._output(f"   {spell.description}")
            self._output(f"   💧 Mana: {spell.mana_cost}  ⚔️  Schaden: {spell.damage}")

    async def send_direct_message(self, recipient_name: str, message: str):
        """Sendet direkte Nachricht an Spieler"""
        if not self.stub or not self.player_id:
            logger.error("Nicht eingeloggt")
            return

        request = dungeon_pb2.SendDirectMessageRequest(
            sender_id=self.player_id, recipient_name=recipient_name, message=message
        )
        response = await self.stub.SendDirectMessage(request)
        self._output(f"\n{response.message}")

    async def send_room_message(self, message: str):
        """Sendet Nachricht an alle im Raum"""
        if not self.stub or not self.player_id:
            logger.error("Nicht eingeloggt")
            return

        request = dungeon_pb2.SendRoomMessageRequest(
            sender_id=self.player_id, message=message
        )
        response = await self.stub.SendRoomMessage(request)
        if not response.success:
            self._output(f"\n{response.message}")

    async def send_broadcast_message(self, message: str):
        """Sendet Broadcast an alle Spieler"""
        if not self.stub or not self.player_id:
            logger.error("Nicht eingeloggt")
            return

        request = dungeon_pb2.SendBroadcastMessageRequest(
            sender_id=self.player_id, message=message
        )
        response = await self.stub.SendBroadcastMessage(request)
        if not response.success:
            self._output(f"\n{response.message}")

    async def get_online_players(self):
        """Zeigt Liste aller Online-Spieler"""
        if not self.stub or not self.player_id:
            logger.error("Nicht eingeloggt")
            return

        request = dungeon_pb2.GetOnlinePlayersRequest(player_id=self.player_id)
        response = await self.stub.GetOnlinePlayers(request)

        self._output(f"\n=== Online Spieler ({len(response.players)}) ===")
        for player in response.players:
            self._output(f"  • {player.name} - {player.room_name}")

    async def open_chest(self, chest_name: str):
        """Öffnet eine Kiste"""
        if not self.stub or not self.player_id:
            logger.error("Nicht eingeloggt")
            return

        request = dungeon_pb2.OpenChestRequest(
            player_id=self.player_id, chest_name=chest_name
        )
        response = await self.stub.OpenChest(request)
        self._output(f"\n{response.message}")

    async def close_chest(self, chest_name: str):
        """Schließt eine Kiste"""
        if not self.stub or not self.player_id:
            logger.error("Nicht eingeloggt")
            return

        request = dungeon_pb2.CloseChestRequest(
            player_id=self.player_id, chest_name=chest_name
        )
        response = await self.stub.CloseChest(request)
        self._output(f"\n{response.message}")

    async def put_in_chest(self, item_name: str, chest_name: str):
        """Legt Item in Kiste"""
        if not self.stub or not self.player_id:
            logger.error("Nicht eingeloggt")
            return

        request = dungeon_pb2.PutInChestRequest(
            player_id=self.player_id, item_name=item_name, chest_name=chest_name
        )
        response = await self.stub.PutInChest(request)
        self._output(f"\n{response.message}")

    async def get_from_chest(self, item_name: str, chest_name: str):
        """Holt Item aus Kiste"""
        if not self.stub or not self.player_id:
            logger.error("Nicht eingeloggt")
            return

        request = dungeon_pb2.GetFromChestRequest(
            player_id=self.player_id, item_name=item_name, chest_name=chest_name
        )
        response = await self.stub.GetFromChest(request)
        self._output(f"\n{response.message}")

    async def inspect_chest(self, chest_name: str):
        """Inspiziert eine Kiste"""
        if not self.stub or not self.player_id:
            logger.error("Nicht eingeloggt")
            return

        request = dungeon_pb2.InspectChestRequest(
            player_id=self.player_id, chest_name=chest_name
        )

        try:
            response = await self.stub.InspectChest(request)
        except Exception as e:
            logger.error(f"RPC call failed: {e}")
            self._output(f"\nFehler beim RPC-Aufruf: {e}")
            return

        if response.success and response.HasField("chest"):
            chest = response.chest
            self._output(f"\n{'=' * 50}")
            self._output(f"📦 {chest.name}")
            self._output(f"{'=' * 50}")
            self._output(f"{chest.description}")
            status_icon = "🔓" if chest.is_open else "🔒"
            status_text = "offen" if chest.is_open else "geschlossen"
            self._output(f"\nStatus: {status_icon} {status_text}")

            if chest.is_open:
                if chest.items:
                    self._output(f"\n💎 Inhalt ({len(chest.items)} Items):")
                    for item in chest.items:
                        self._output(f"  • {item.name}")
                        self._output(f"    {item.description}")
                        self._output(f"    Wert: {item.value} Gold")
                else:
                    self._output(f"\nDie Kiste ist leer.")
            else:
                self._output(
                    f"\nDu musst die Kiste erst öffnen, um den Inhalt zu sehen."
                )
            self._output(f"{'=' * 50}")
        else:
            self._output(f"\n{response.message}")

    def _print_room(self, room: dungeon_pb2.RoomInfo):
        """Gibt Raum-Information formatiert aus"""
        output = []
        output.append(f"\n{'=' * 60}")
        output.append(f"📍 {room.name}")
        output.append(f"{'=' * 60}")
        output.append(f"{room.description}")
        output.append("")

        if room.exits:
            output.append(f"🚪 Ausgänge: {', '.join(room.exits)}")

        if room.items:
            output.append(f"\n💎 Items im Raum:")
            for item in room.items:
                output.append(
                    f"  - {item.name} (ID: {item.item_id}): {item.description}"
                )

        if room.chests:
            output.append(f"\n📦 Kisten im Raum:")
            for chest in room.chests:
                status = "🔓 offen" if chest.is_open else "🔒 geschlossen"
                item_count = f" ({len(chest.items)} Items)" if chest.is_open else ""
                output.append(f"  - {chest.name} [{status}]{item_count}")
                output.append(f"    {chest.description}")

        if room.npcs:
            output.append(f"\n👤 NPCs:")
            for npc in room.npcs:
                hostile = "⚔️ FEINDLICH" if npc.is_hostile else "🤝 Friedlich"
                output.append(f"  - {npc.name} (ID: {npc.npc_id}) [{hostile}]")
                output.append(
                    f"    {npc.description} (HP: {npc.health}, MP: {npc.magic})"
                )

        if room.players:
            output.append(f"\n👥 Andere Spieler: {', '.join(room.players)}")

        output.append(f"{'=' * 60}\n")
        self._output("\n".join(output))

    async def _stream_events(self):
        """Empfängt und verarbeitet Game Events (läuft als async Task)"""
        if not self.stub or not self.player_id:
            return

        request = dungeon_pb2.StreamEventsRequest(player_id=self.player_id)

        try:
            async for event in self.stub.StreamEvents(request):
                if self.stop_events.is_set():
                    break

                event_type = dungeon_pb2.GameEvent.EventType.Name(event.event_type)

                # Formatiere Nachrichten basierend auf Typ
                if event_type in [
                    "DIRECT_MESSAGE",
                    "ROOM_MESSAGE",
                    "BROADCAST_MESSAGE",
                ]:
                    # Nachrichten mit speziellem Präfix
                    if event_type == "DIRECT_MESSAGE":
                        self._output(f"\n💬 {event.message}")
                    elif event_type == "ROOM_MESSAGE":
                        self._output(f"\n💭 {event.message}")
                    elif event_type == "BROADCAST_MESSAGE":
                        self._output(f"\n📢 {event.message}")
                else:
                    # Standard Events
                    self._output(f"\n🔔 EVENT: {event.message}")
        except asyncio.CancelledError:
            logger.info("Event Stream gestoppt")
        except Exception as e:
            if not self.stop_events.is_set():
                logger.error(f"Event Stream Fehler: {e}")


async def interactive_client():
    """Interaktiver Client mit prompt-toolkit UI"""
    client = DungeonClient()

    # TextArea für Output (read-only, aber fokussierbar für Textauswahl)
    output_field = TextArea(
        text="=== Multi-User Dungeon Client ===\n",
        multiline=True,
        scrollbar=True,
        read_only=True,
        focusable=True,
        style="class:output-field",
    )

    # Command History für Input
    command_history = InMemoryHistory()

    # TextArea für Input mit History (Up/Down Navigation)
    input_field = TextArea(
        height=1,
        prompt=">>> ",
        multiline=False,
        wrap_lines=False,
        history=command_history,
        style="class:input-field",
    )

    # Info-Bar
    info_bar = Window(
        content=FormattedTextControl(
            text="Enter: Senden | ↑↓: History | Tab: Wechseln | Ctrl+C: Beenden"
        ),
        height=1,
        style="class:info-bar",
    )

    # Status-Fenster (rechts)
    status_field = TextArea(
        text="=== Status ===\n\nLade...",
        multiline=True,
        scrollbar=True,
        read_only=True,
        focusable=False,
        style="class:output-field",
    )

    # Layout: Links Haupt-Interface, rechts Status
    left_container = HSplit(
        [
            output_field,
            Window(height=1, char="-", style="class:line"),
            input_field,
            info_bar,
        ]
    )

    root_container = VSplit(
        [
            left_container,
            Window(width=1, char="|", style="class:line"),
            status_field,
        ]
    )

    layout = Layout(root_container, focused_element=input_field)

    # Output Callback
    def append_output(text: str):
        """Fügt Text zum Output hinzu"""
        current_text = output_field.text
        output_field.text = current_text + text + "\n"
        # Scrolle nach unten
        output_field.buffer.cursor_position = len(output_field.text)

    client.set_output_callback(append_output)

    # Status Update Funktion
    async def update_status():
        """Aktualisiert Status-Fenster alle 2 Sekunden"""
        while True:
            try:
                await asyncio.sleep(2)
                if client.stub and client.player_id:
                    request = dungeon_pb2.GetPlayerInfoRequest(
                        player_id=client.player_id
                    )
                    response = await client.stub.GetPlayerInfo(request)

                    status_text = []
                    status_text.append("=== Status ===")
                    status_text.append("")
                    status_text.append(f"Spieler: {response.name}")
                    status_text.append(f"❤️  Health: {response.health}")
                    status_text.append(f"✨ Magic: {response.magic}")
                    status_text.append("")
                    status_text.append(f"🎒 Inventar ({len(response.inventory)}):")
                    if response.inventory:
                        for item in response.inventory:
                            status_text.append(f"  • {item.name}")
                            status_text.append(f"    Wert: {item.value}")
                    else:
                        status_text.append("  (leer)")

                    status_field.text = "\n".join(status_text)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Status Update Fehler: {e}")

    # Key Bindings
    kb = KeyBindings()

    @kb.add("enter")
    def _(event):
        """Verarbeite Eingabe"""
        command = input_field.buffer.text.strip()

        if not command:
            return

        # Füge zur History hinzu BEVOR wir das Feld leeren
        command_history.append_string(command)

        # Zeige Kommando im Output
        append_output(f"[{client.player_name or 'User'}]> {command}")

        # Leere das Eingabefeld
        input_field.buffer.reset()

        # Verarbeite Kommando asynchron
        asyncio.create_task(process_command(command, event.app))

    async def process_command(command: str, app):
        """Verarbeitet Kommandos asynchron"""
        parts = command.split(maxsplit=1)
        cmd = parts[0].lower()
        arg = parts[1] if len(parts) > 1 else None

        try:
            if cmd == "quit" or cmd == "exit":
                app.exit()
            elif cmd == "move" and arg:
                await client.move(arg)
            elif cmd == "look":
                await client.look_around()
            elif cmd == "take" and arg:
                await client.take_item(arg)
            elif cmd == "drop" and arg:
                await client.drop_item(arg)
            elif cmd == "open" and arg:
                await client.open_chest(arg)
            elif cmd == "close" and arg:
                await client.close_chest(arg)
            elif cmd in ["inspect", "untersuche", "betrachte"] and arg:
                await client.inspect_chest(arg)
            elif cmd == "put" and arg:
                # Format: put <item> <chest>
                put_parts = arg.split(maxsplit=1)
                if len(put_parts) == 2:
                    await client.put_in_chest(put_parts[0], put_parts[1])
                else:
                    append_output("Verwendung: put <item> <kiste>")
            elif cmd == "get" and arg:
                # Format: get <item> <chest>
                get_parts = arg.split(maxsplit=1)
                if len(get_parts) == 2:
                    await client.get_from_chest(get_parts[0], get_parts[1])
                else:
                    append_output("Verwendung: get <item> <kiste>")
            elif cmd == "talk" and arg:
                await client.talk_to_npc(arg)
            elif cmd == "attack" and arg:
                await client.attack_npc(arg)
            elif cmd == "info":
                await client.get_player_info()
            elif cmd == "read" and arg:
                await client.read_scroll(arg)
            elif cmd == "cast" and arg:
                # Format: cast <spell> [target]
                cast_parts = arg.split(maxsplit=1)
                spell_name = cast_parts[0]
                target_id = cast_parts[1] if len(cast_parts) > 1 else ""
                await client.cast_spell(spell_name, target_id)
            elif cmd in ["spellbook", "spells"]:
                await client.list_spellbook()
            elif cmd == "msg" and arg:
                msg_parts = arg.split(maxsplit=1)
                if len(msg_parts) == 2:
                    await client.send_direct_message(msg_parts[0], msg_parts[1])
                else:
                    append_output("Verwendung: msg <spielername> <nachricht>")
            elif cmd == "say" and arg:
                await client.send_room_message(arg)
            elif cmd == "shout" and arg:
                await client.send_broadcast_message(arg)
            elif cmd == "who":
                await client.get_online_players()
            elif cmd == "history":
                # Zeige Befehlshistorie
                history_strings = list(command_history.load_history_strings())
                if history_strings:
                    append_output("\n=== Befehlshistorie ===")
                    for i, hist_cmd in enumerate(history_strings, 1):
                        append_output(f"{i:3d}  {hist_cmd}")
                    append_output(f"\nGesamt: {len(history_strings)} Befehle")
                else:
                    append_output("\nKeine Befehle in der Historie.")
            elif cmd == "help":
                help_text = """
=== Kommandos ===
move <direction>        - Bewege dich (north, south, east, west)
look                    - Schau dich um
take <item>             - Nimm Item auf (z.B. take fackel oder take fackel 2)
drop <item>             - Lege Item ab
open <chest>            - Öffne Kiste (z.B. open holzkiste)
close <chest>           - Schließe Kiste
inspect/untersuche <x>  - Untersuche Kiste (zeigt Inhalt wenn offen)
                          z.B. inspect holzkiste, untersuche schatztruhe
put <item> <chest>      - Lege Item in Kiste (z.B. put fackel holzkiste)
get <item> <chest>      - Hole Item aus Kiste (z.B. get seil holzkiste)
                          Mit Index: get diamant 2 schatztruhe
talk <npc_id>           - Sprich mit NPC
attack <npc_id>         - Greife NPC an
info                    - Zeige Spieler-Info
read <rolle>            - Lese Zauberspruchrolle und lerne Zauber
cast <zauber> [ziel]    - Wirke Zauberspruch (z.B. cast Feuerfunke Schatzdrache)
spellbook/spells        - Zeige dein Zauberbuch
msg <name> <text>       - Direkte Nachricht an Spieler
say <text>              - Nachricht an alle im Raum
shout <text>            - Broadcast an alle Spieler
who                     - Zeige Online-Spieler
history                 - Zeige Befehlshistorie
help                    - Zeige Kommandos
quit/exit               - Beende Client
"""
                append_output(help_text)
            elif cmd == "clear":
                output_field.text = ""
            else:
                append_output(f"Unbekanntes Kommando: '{cmd}'. Nutze 'help' für Hilfe.")
        except Exception as e:
            append_output(f"Fehler: {str(e)}")
            logger.error(f"Kommando-Fehler: {e}", exc_info=True)

    @kb.add("c-c")
    def _(event):
        """Ctrl+C zum Kopieren oder Beenden"""
        # Prüfe ob Text im Output-Fenster selektiert ist (unabhängig vom Fokus)
        if output_field.buffer.selection_state:
            # Hole markierten Text
            selection = output_field.buffer.copy_selection()
            if selection:
                try:
                    # Kopiere in System-Zwischenablage (plattformunabhängig)
                    event.app.clipboard.set_data(ClipboardData(selection.text))
                    # Fokus bleibt wo er ist, keine Bestätigung nötig
                except Exception as e:
                    logger.error(f"Kopieren fehlgeschlagen: {e}")
            return
        # Sonst beende die App
        event.app.exit()

    @kb.add("tab")
    def _(event):
        """Tab: Wechsle zwischen Output und Input"""
        if event.app.layout.has_focus(output_field):
            event.app.layout.focus(input_field)
        else:
            event.app.layout.focus(output_field)

    @kb.add("escape")
    def _(event):
        """Escape: Fokus zurück zum Input"""
        event.app.layout.focus(input_field)

    # Application (merge bindings damit TextArea Up/Down funktioniert)
    bindings_list = [kb]
    if input_field.control.key_bindings:
        bindings_list.append(input_field.control.key_bindings)

    app = Application(
        layout=layout,
        key_bindings=merge_key_bindings(bindings_list),
        full_screen=True,
        mouse_support=True,
        style=ui_style,
    )

    # Verbinde zum Server
    append_output("Verbinde mit Server...")
    try:
        await client.connect()
        append_output("✓ Verbunden!")
    except Exception as e:
        append_output(f"✗ Fehler beim Verbinden: {e}")
        return

    # Login (vor dem Start der App)
    from prompt_toolkit.shortcuts import input_dialog

    player_name = await input_dialog(
        title="Login",
        text="Gib deinen Spielernamen ein:",
    ).run_async()

    if not player_name or not player_name.strip():
        append_output("Ungültiger Name. Beende...")
        await client.disconnect()
        return

    player_name = player_name.strip()

    password = await input_dialog(
        title="Login",
        text=f"Passwort für '{player_name}':",
        password=True,
    ).run_async()

    if not password:
        append_output("Kein Passwort eingegeben. Beende...")
        await client.disconnect()
        return

    append_output(f"Anmelden als '{player_name}'...")

    if not await client.register(player_name, password):
        await client.disconnect()
        return

    append_output("✓ Erfolgreich angemeldet!")

    # Zeige aktuellen Raum
    await client.look_around()

    # Zeige Hilfe
    append_output("\nNutze 'help' für eine Liste aller Kommandos.")

    # Starte Status-Update Task
    status_task = asyncio.create_task(update_status())

    try:
        # Starte Application mit asyncio
        await app.run_async()
    finally:
        # Stoppe Status-Update
        status_task.cancel()
        try:
            await status_task
        except asyncio.CancelledError:
            pass

        append_output("\nTschüss!")
        await client.disconnect()


def main():
    """Entry point für den Client"""
    asyncio.run(interactive_client())


if __name__ == "__main__":
    main()
