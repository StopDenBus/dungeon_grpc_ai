"""
gRPC Client für das Multi-User Dungeon
"""

import logging
import threading
from typing import Optional
from datetime import datetime
import grpc
from prompt_toolkit import Application
from prompt_toolkit.buffer import Buffer
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.layout.containers import HSplit, Window
from prompt_toolkit.layout.controls import BufferControl, FormattedTextControl
from prompt_toolkit.layout.layout import Layout
from prompt_toolkit.styles import Style
from prompt_toolkit.widgets import SearchToolbar, TextArea
from . import dungeon_pb2
from . import dungeon_pb2_grpc

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

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
        self.channel: Optional[grpc.Channel] = None
        self.stub: Optional[dungeon_pb2_grpc.DungeonServiceStub] = None
        self.player_id: Optional[str] = None
        self.player_name: Optional[str] = None
        self.event_thread: Optional[threading.Thread] = None
        self.stop_events = threading.Event()
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

    def connect(self):
        """Verbindet mit dem Server"""
        self.channel = grpc.insecure_channel(self.server_address)
        self.stub = dungeon_pb2_grpc.DungeonServiceStub(self.channel)
        logger.info(f"Verbunden mit Server: {self.server_address}")

    def disconnect(self):
        """Trennt Verbindung zum Server"""
        # Melde Spieler ordentlich ab
        if self.stub and self.player_id:
            try:
                request = dungeon_pb2.UnregisterPlayerRequest(player_id=self.player_id)
                response = self.stub.UnregisterPlayer(request)
                if response.success:
                    logger.info(response.message)
            except Exception as e:
                logger.error(f"Fehler beim Abmelden: {e}")

        # Stoppe Event Thread
        if self.event_thread and self.event_thread.is_alive():
            self.stop_events.set()
            self.event_thread.join(timeout=2)

        if self.channel:
            self.channel.close()
            logger.info("Verbindung getrennt")

    def register(self, player_name: str, password: str) -> bool:
        """Registriert Spieler beim Server oder meldet bestehenden an."""
        if not self.stub:
            logger.error("Nicht mit Server verbunden")
            return False

        request = dungeon_pb2.RegisterPlayerRequest(
            player_name=player_name, password=password
        )
        response = self.stub.RegisterPlayer(request)

        if response.success:
            self.player_id = response.player_id
            self.player_name = player_name
            logger.info(response.message)

            # Starte Event Stream in separatem Thread
            self.event_thread = threading.Thread(
                target=self._stream_events, daemon=True
            )
            self.event_thread.start()
            return True
        else:
            logger.error(response.message)
            self._output(f"✗ {response.message}")
            return False

    def move(self, direction: str) -> bool:
        """Bewegt Spieler in eine Richtung"""
        if not self.stub or not self.player_id:
            logger.error("Nicht eingeloggt")
            return False

        request = dungeon_pb2.MovePlayerRequest(
            player_id=self.player_id, direction=direction
        )
        response = self.stub.MovePlayer(request)

        self._output(f"\n{response.message}")
        if response.success and response.HasField("new_room"):
            self._print_room(response.new_room)

        return response.success

    def look_around(self):
        """Schaut sich im aktuellen Raum um"""
        if not self.stub or not self.player_id:
            logger.error("Nicht eingeloggt")
            return

        request = dungeon_pb2.LookAroundRequest(player_id=self.player_id)
        response = self.stub.LookAround(request)

        if response.HasField("room"):
            self._print_room(response.room)

    def take_item(self, item_id: str):
        """Nimmt Item auf"""
        if not self.stub or not self.player_id:
            logger.error("Nicht eingeloggt")
            return

        request = dungeon_pb2.TakeItemRequest(player_id=self.player_id, item_id=item_id)
        response = self.stub.TakeItem(request)
        self._output(f"\n{response.message}")

    def drop_item(self, item_id: str):
        """Legt Item ab"""
        if not self.stub or not self.player_id:
            logger.error("Nicht eingeloggt")
            return

        request = dungeon_pb2.DropItemRequest(player_id=self.player_id, item_id=item_id)
        response = self.stub.DropItem(request)
        self._output(f"\n{response.message}")

    def talk_to_npc(self, npc_id: str):
        """Spricht mit NPC"""
        if not self.stub or not self.player_id:
            logger.error("Nicht eingeloggt")
            return

        request = dungeon_pb2.TalkToNPCRequest(player_id=self.player_id, npc_id=npc_id)
        response = self.stub.TalkToNPC(request)

        self._output(f"\n{response.message}")
        if response.success:
            self._output(f"'{response.npc_response}'")

    def attack_npc(self, npc_id: str):
        """Greift NPC an"""
        if not self.stub or not self.player_id:
            logger.error("Nicht eingeloggt")
            return

        request = dungeon_pb2.AttackNPCRequest(player_id=self.player_id, npc_id=npc_id)
        response = self.stub.AttackNPC(request)

        self._output(f"\n{response.message}")
        if response.success:
            self._output(
                f"Schaden: {response.damage_dealt}, Verbleibende Health: {response.npc_health_remaining}"
            )

    def get_player_info(self):
        """Zeigt Spieler-Information"""
        if not self.stub or not self.player_id:
            logger.error("Nicht eingeloggt")
            return

        request = dungeon_pb2.GetPlayerInfoRequest(player_id=self.player_id)
        response = self.stub.GetPlayerInfo(request)

        self._output(f"\n=== Spieler Info ===")
        self._output(f"Name: {response.name}")
        self._output(f"Health: {response.health}")
        self._output(f"Magic: {response.magic}")
        self._output(f"Inventar ({len(response.inventory)} Items):")
        for item in response.inventory:
            self._output(
                f"  - {item.name} (ID: {item.item_id}): {item.description} [Wert: {item.value}]"
            )

    def send_direct_message(self, recipient_name: str, message: str):
        """Sendet direkte Nachricht an Spieler"""
        if not self.stub or not self.player_id:
            logger.error("Nicht eingeloggt")
            return

        request = dungeon_pb2.SendDirectMessageRequest(
            sender_id=self.player_id, recipient_name=recipient_name, message=message
        )
        response = self.stub.SendDirectMessage(request)
        self._output(f"\n{response.message}")

    def send_room_message(self, message: str):
        """Sendet Nachricht an alle im Raum"""
        if not self.stub or not self.player_id:
            logger.error("Nicht eingeloggt")
            return

        request = dungeon_pb2.SendRoomMessageRequest(
            sender_id=self.player_id, message=message
        )
        response = self.stub.SendRoomMessage(request)
        if not response.success:
            self._output(f"\n{response.message}")

    def send_broadcast_message(self, message: str):
        """Sendet Broadcast an alle Spieler"""
        if not self.stub or not self.player_id:
            logger.error("Nicht eingeloggt")
            return

        request = dungeon_pb2.SendBroadcastMessageRequest(
            sender_id=self.player_id, message=message
        )
        response = self.stub.SendBroadcastMessage(request)
        if not response.success:
            self._output(f"\n{response.message}")

    def get_online_players(self):
        """Zeigt Liste aller Online-Spieler"""
        if not self.stub or not self.player_id:
            logger.error("Nicht eingeloggt")
            return

        request = dungeon_pb2.GetOnlinePlayersRequest(player_id=self.player_id)
        response = self.stub.GetOnlinePlayers(request)

        self._output(f"\n=== Online Spieler ({len(response.players)}) ===")
        for player in response.players:
            self._output(f"  • {player.name} - {player.room_name}")

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

    def _stream_events(self):
        """Empfängt und verarbeitet Game Events (läuft in separatem Thread)"""
        if not self.stub or not self.player_id:
            return

        request = dungeon_pb2.StreamEventsRequest(player_id=self.player_id)

        try:
            for event in self.stub.StreamEvents(request):
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
        except Exception as e:
            if not self.stop_events.is_set():
                logger.error(f"Event Stream Fehler: {e}")


def interactive_client():
    """Interaktiver Client mit prompt-toolkit UI"""
    client = DungeonClient()

    # TextArea für Output (read-only)
    output_field = TextArea(
        text="=== Multi-User Dungeon Client ===\n",
        multiline=True,
        scrollbar=True,
        read_only=True,
        focusable=False,
        style="class:output-field",
    )

    # TextArea für Input mit SearchToolbar
    search_toolbar = SearchToolbar()
    input_field = TextArea(
        height=1,
        prompt=">>> ",
        multiline=False,
        wrap_lines=False,
        search_field=search_toolbar,
        style="class:input-field",
    )

    # Info-Bar
    info_bar = Window(
        content=FormattedTextControl(
            text="Drücke Enter zum Senden | Ctrl+C zum Beenden"
        ),
        height=1,
        style="class:info-bar",
    )

    # Layout
    root_container = HSplit(
        [
            output_field,
            Window(height=1, char="-", style="class:line"),
            input_field,
            search_toolbar,
            info_bar,
        ]
    )

    layout = Layout(root_container)

    # Output Callback
    def append_output(text: str):
        """Fügt Text zum Output hinzu"""
        current_text = output_field.text
        output_field.text = current_text + text + "\n"
        # Scrolle nach unten
        output_field.buffer.cursor_position = len(output_field.text)

    client.set_output_callback(append_output)

    # Key Bindings
    kb = KeyBindings()

    @kb.add("enter")
    def _(event):
        """Verarbeite Eingabe"""
        command = input_field.text.strip()
        input_field.text = ""

        if not command:
            return

        # Zeige Kommando im Output
        append_output(f"[{client.player_name or 'User'}]> {command}")

        # Verarbeite Kommando
        parts = command.split(maxsplit=1)
        cmd = parts[0].lower()
        arg = parts[1] if len(parts) > 1 else None

        try:
            if cmd == "quit" or cmd == "exit":
                event.app.exit()
            elif cmd == "move" and arg:
                client.move(arg)
            elif cmd == "look":
                client.look_around()
            elif cmd == "take" and arg:
                client.take_item(arg)
            elif cmd == "drop" and arg:
                client.drop_item(arg)
            elif cmd == "talk" and arg:
                client.talk_to_npc(arg)
            elif cmd == "attack" and arg:
                client.attack_npc(arg)
            elif cmd == "info":
                client.get_player_info()
            elif cmd == "msg" and arg:
                msg_parts = arg.split(maxsplit=1)
                if len(msg_parts) == 2:
                    client.send_direct_message(msg_parts[0], msg_parts[1])
                else:
                    append_output("Verwendung: msg <spielername> <nachricht>")
            elif cmd == "say" and arg:
                client.send_room_message(arg)
            elif cmd == "shout" and arg:
                client.send_broadcast_message(arg)
            elif cmd == "who":
                client.get_online_players()
            elif cmd == "help":
                help_text = """
=== Kommandos ===
move <direction>    - Bewege dich (north, south, east, west)
look                - Schau dich um
take <item_id>      - Nimm Item auf
drop <item_id>      - Lege Item ab
talk <npc_id>       - Sprich mit NPC
attack <npc_id>     - Greife NPC an
info                - Zeige Spieler-Info
msg <name> <text>   - Direkte Nachricht an Spieler
say <text>          - Nachricht an alle im Raum
shout <text>        - Broadcast an alle Spieler
who                 - Zeige Online-Spieler
help                - Zeige Kommandos
quit/exit           - Beende Client
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
        """Ctrl+C zum Beenden"""
        event.app.exit()

    # Application
    app = Application(
        layout=layout,
        key_bindings=kb,
        full_screen=True,
        mouse_support=True,
        style=ui_style,
    )

    # Verbinde zum Server
    append_output("Verbinde mit Server...")
    try:
        client.connect()
        append_output("✓ Verbunden!")
    except Exception as e:
        append_output(f"✗ Fehler beim Verbinden: {e}")
        return

    # Login (vor dem Start der App)
    from prompt_toolkit.shortcuts import input_dialog

    player_name = input_dialog(
        title="Login",
        text="Gib deinen Spielernamen ein:",
    ).run()

    if not player_name or not player_name.strip():
        append_output("Ungültiger Name. Beende...")
        client.disconnect()
        return

    player_name = player_name.strip()

    password = input_dialog(
        title="Login",
        text=f"Passwort für '{player_name}':",
        password=True,
    ).run()

    if not password:
        append_output("Kein Passwort eingegeben. Beende...")
        client.disconnect()
        return

    append_output(f"Anmelden als '{player_name}'...")

    if not client.register(player_name, password):
        client.disconnect()
        return

    append_output("✓ Erfolgreich angemeldet!")

    # Zeige aktuellen Raum
    client.look_around()

    # Zeige Hilfe
    append_output("\nNutze 'help' für eine Liste aller Kommandos.")

    try:
        # Starte Application
        app.run()
    finally:
        append_output("\nTschüss!")
        client.disconnect()


def main():
    """Entry point für den Client"""
    interactive_client()


if __name__ == "__main__":
    main()
