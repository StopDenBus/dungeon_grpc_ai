"""
Textual TUI Client für das Multi-User Dungeon
"""

import asyncio
import logging
from typing import Optional
from datetime import datetime
from pathlib import Path
import grpc.aio
from textual.app import App, ComposeResult
from textual.containers import Container, Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Header, Footer, Input, RichLog, Static, Button, Label
from textual.binding import Binding
from textual.reactive import reactive
from textual.suggester import Suggester
from textual import work
from rich.text import Text
from . import dungeon_pb2
from . import dungeon_pb2_grpc

# Logging Setup - schreibt in Datei
log_dir = Path.home() / ".dungeon" / "logs"
log_dir.mkdir(parents=True, exist_ok=True)
log_file = log_dir / f"client_textual_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler(log_file),
    ],
)
logger = logging.getLogger(__name__)
logger.info(f"Textual Client logging to: {log_file}")


class HistorySuggester(Suggester):
    """Suggester der Vorschläge aus der Befehlshistorie liefert"""

    def __init__(self, app_instance):
        super().__init__(use_cache=False, case_sensitive=False)
        self.app_instance = app_instance

    async def get_suggestion(self, value: str) -> str | None:
        """Gibt Vorschlag basierend auf aktuellem Input zurück"""
        if not value:
            return None

        # Durchsuche Historie rückwärts (neueste zuerst)
        for command in reversed(self.app_instance.command_history):
            if command.startswith(value) and command != value:
                return command

        return None


class StatusPanel(Static):
    """Status-Anzeige Panel"""

    player_name = reactive("")
    health = reactive(0)
    magic = reactive(0)
    room_name = reactive("Unbekannt")

    def render(self) -> str:
        """Rendert den Status"""
        return f"""[bold cyan]Status[/bold cyan]
━━━━━━━━━━━━━━━━━━━━━━
Spieler: [yellow]{self.player_name or "-"}[/yellow]
Raum: [green]{self.room_name}[/green]
❤️  HP: [red]{self.health}[/red]
✨ MP: [blue]{self.magic}[/blue]
"""


class InventoryPanel(Static):
    """Inventar-Anzeige Panel"""

    inventory_items = reactive([])

    def render(self) -> str:
        """Rendert das Inventar"""
        lines = ["[bold cyan]🎒 Inventar[/bold cyan]", "━━━━━━━━━━━━━━━━━━━━━━", ""]

        if self.inventory_items:
            for item in self.inventory_items:
                # Kürze Namen wenn zu lang
                name = item if len(item) <= 18 else item[:15] + "..."
                lines.append(f"• [yellow]{name}[/yellow]")
        else:
            lines.append("[dim](leer)[/dim]")

        # Füge Leerzeilen hinzu damit Panel Platz einnimmt
        while len(lines) < 10:
            lines.append("")

        return "\n".join(lines)


class NavigationPanel(Static):
    """Navigations-Panel mit Richtungstasten"""

    available_exits = reactive([])

    def compose(self) -> ComposeResult:
        """Erstellt die Navigation Buttons"""
        with Container(id="nav-container"):
            yield Static("[bold]Navigation[/bold]", id="nav-title")
            with Horizontal(id="nav-row-1"):
                yield Static("", classes="nav-spacer")
                yield Button("⬆ Nord", id="btn-north", variant="primary")
                yield Static("", classes="nav-spacer")
            with Horizontal(id="nav-row-2"):
                yield Button("⬅ West", id="btn-west", variant="primary")
                yield Button("👁 Look", id="btn-look", variant="success")
                yield Button("➡ Ost", id="btn-east", variant="primary")
            with Horizontal(id="nav-row-3"):
                yield Static("", classes="nav-spacer")
                yield Button("⬇ Süd", id="btn-south", variant="primary")
                yield Static("", classes="nav-spacer")

    def watch_available_exits(self, exits: list) -> None:
        """Aktualisiert Button-Status basierend auf verfügbaren Ausgängen"""
        if not exits:
            return

        # Aktualisiere Button disabled State
        for direction in ["north", "south", "east", "west"]:
            btn = self.query_one(f"#btn-{direction}", Button)
            btn.disabled = direction not in exits


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
        self.status_callback = None  # Callback für Status-Updates

    def set_output_callback(self, callback):
        """Setzt Callback für Output-Updates"""
        self.output_callback = callback

    def set_status_callback(self, callback):
        """Setzt Callback für Status-Updates"""
        self.status_callback = callback

    def _output(self, text: str, style: str = ""):
        """Sendet Output an Callback"""
        if self.output_callback:
            self.output_callback(text, style)

    def _update_status(self, **kwargs):
        """Sendet Status-Update an Callback"""
        if self.status_callback:
            self.status_callback(**kwargs)

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
            self._output(response.message, "success")
            self._update_status(player_name=player_name)

            # Starte Event Stream
            self.event_task = asyncio.create_task(self._stream_events())
            return True
        else:
            logger.error(response.message)
            self._output(response.message, "error")
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

        self._output(f"\n{response.message}", "info")
        if response.success and response.HasField("new_room"):
            self._print_room(response.new_room)
            await self._update_player_info()

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
            await self._update_player_info()

    async def take_item(self, item_id: str):
        """Nimmt Item auf"""
        if not self.stub or not self.player_id:
            logger.error("Nicht eingeloggt")
            return

        request = dungeon_pb2.TakeItemRequest(player_id=self.player_id, item_id=item_id)
        response = await self.stub.TakeItem(request)
        self._output(f"\n{response.message}", "info")
        await self._update_player_info()

    async def drop_item(self, item_id: str):
        """Legt Item ab"""
        if not self.stub or not self.player_id:
            logger.error("Nicht eingeloggt")
            return

        request = dungeon_pb2.DropItemRequest(player_id=self.player_id, item_id=item_id)
        response = await self.stub.DropItem(request)
        self._output(f"\n{response.message}", "info")
        await self._update_player_info()

    async def talk_to_npc(self, npc_id: str):
        """Spricht mit NPC"""
        if not self.stub or not self.player_id:
            logger.error("Nicht eingeloggt")
            return

        request = dungeon_pb2.TalkToNPCRequest(player_id=self.player_id, npc_id=npc_id)
        response = await self.stub.TalkToNPC(request)

        self._output(f"\n{response.message}", "info")
        if response.success:
            self._output(f"'{response.npc_response}'", "npc")

    async def attack_npc(self, npc_id: str):
        """Greift NPC an"""
        if not self.stub or not self.player_id:
            logger.error("Nicht eingeloggt")
            return

        request = dungeon_pb2.AttackNPCRequest(player_id=self.player_id, npc_id=npc_id)
        response = await self.stub.AttackNPC(request)

        self._output(f"\n{response.message}", "combat")
        if response.success:
            self._output(
                f"Schaden: {response.damage_dealt}, Verbleibende Health: {response.npc_health_remaining}",
                "combat",
            )
        await self._update_player_info()

    async def get_player_info(self):
        """Zeigt Spieler-Information"""
        if not self.stub or not self.player_id:
            logger.error("Nicht eingeloggt")
            return

        request = dungeon_pb2.GetPlayerInfoRequest(player_id=self.player_id)
        response = await self.stub.GetPlayerInfo(request)

        self._output(f"\n[bold cyan]=== Spieler Info ===[/bold cyan]")
        self._output(f"Name: [yellow]{response.name}[/yellow]")
        self._output(f"Health: [red]{response.health}[/red]")
        self._output(f"Magic: [blue]{response.magic}[/blue]")
        self._output(f"Inventar ({len(response.inventory)} Items):")
        for item in response.inventory:
            self._output(f"  - {item.name}: {item.description} [Wert: {item.value}]")

    async def read_scroll(self, item_name: str):
        """Liest eine Zauberspruchrolle"""
        if not self.stub or not self.player_id:
            logger.error("Nicht eingeloggt")
            return

        request = dungeon_pb2.ReadScrollRequest(
            player_id=self.player_id, item_name=item_name
        )
        response = await self.stub.ReadScroll(request)
        self._output(f"\n{response.message}", "magic")
        await self._update_player_info()

    async def cast_spell(self, spell_name: str, target_id: str = ""):
        """Zaubert einen Spruch"""
        if not self.stub or not self.player_id:
            logger.error("Nicht eingeloggt")
            return

        request = dungeon_pb2.CastSpellRequest(
            player_id=self.player_id, spell_name=spell_name, target_id=target_id
        )
        response = await self.stub.CastSpell(request)
        self._output(f"\n{response.message}", "magic")
        await self._update_player_info()

    async def list_spellbook(self):
        """Zeigt Zauberbuch"""
        if not self.stub or not self.player_id:
            logger.error("Nicht eingeloggt")
            return

        request = dungeon_pb2.ListSpellbookRequest(player_id=self.player_id)
        response = await self.stub.ListSpellbook(request)

        if not response.spells:
            self._output(
                "\n[yellow]Dein Zauberbuch ist leer. Finde Zauberspruchrollen um Zauber zu lernen![/yellow]"
            )
            return

        self._output("\n[bold magenta]=== 📖 Zauberbuch ===[/bold magenta]")
        for spell in response.spells:
            self._output(f"\n✨ [bold]{spell.name}[/bold]")
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
        self._output(f"\n{response.message}", "info")

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
            self._output(f"\n{response.message}", "error")

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
            self._output(f"\n{response.message}", "error")

    async def get_online_players(self):
        """Zeigt Liste aller Online-Spieler"""
        if not self.stub or not self.player_id:
            logger.error("Nicht eingeloggt")
            return

        request = dungeon_pb2.GetOnlinePlayersRequest(player_id=self.player_id)
        response = await self.stub.GetOnlinePlayers(request)

        self._output(
            f"\n[bold cyan]=== Online Spieler ({len(response.players)}) ===[/bold cyan]"
        )
        for player in response.players:
            self._output(f"  • [yellow]{player.name}[/yellow] - {player.room_name}")

    async def open_chest(self, chest_name: str):
        """Öffnet eine Kiste"""
        if not self.stub or not self.player_id:
            logger.error("Nicht eingeloggt")
            return

        request = dungeon_pb2.OpenChestRequest(
            player_id=self.player_id, chest_name=chest_name
        )
        response = await self.stub.OpenChest(request)
        self._output(f"\n{response.message}", "info")

    async def close_chest(self, chest_name: str):
        """Schließt eine Kiste"""
        if not self.stub or not self.player_id:
            logger.error("Nicht eingeloggt")
            return

        request = dungeon_pb2.CloseChestRequest(
            player_id=self.player_id, chest_name=chest_name
        )
        response = await self.stub.CloseChest(request)
        self._output(f"\n{response.message}", "info")

    async def put_in_chest(self, item_name: str, chest_name: str):
        """Legt Item in Kiste"""
        if not self.stub or not self.player_id:
            logger.error("Nicht eingeloggt")
            return

        request = dungeon_pb2.PutInChestRequest(
            player_id=self.player_id, item_name=item_name, chest_name=chest_name
        )
        response = await self.stub.PutInChest(request)
        self._output(f"\n{response.message}", "info")

    async def get_from_chest(self, item_name: str, chest_name: str):
        """Holt Item aus Kiste"""
        if not self.stub or not self.player_id:
            logger.error("Nicht eingeloggt")
            return

        request = dungeon_pb2.GetFromChestRequest(
            player_id=self.player_id, item_name=item_name, chest_name=chest_name
        )
        response = await self.stub.GetFromChest(request)
        self._output(f"\n{response.message}", "info")

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
            self._output(f"\nFehler beim RPC-Aufruf: {e}", "error")
            return

        if response.success and response.HasField("chest"):
            chest = response.chest
            self._output(f"\n[bold]{'=' * 50}[/bold]")
            self._output(f"[bold cyan]📦 {chest.name}[/bold cyan]")
            self._output(f"[bold]{'=' * 50}[/bold]")
            self._output(f"{chest.description}")
            status_icon = "🔓" if chest.is_open else "🔒"
            status_text = "offen" if chest.is_open else "geschlossen"
            self._output(f"\nStatus: {status_icon} {status_text}")

            if chest.is_open:
                if chest.items:
                    self._output(f"\n💎 Inhalt ({len(chest.items)} Items):")
                    for item in chest.items:
                        self._output(f"  • [yellow]{item.name}[/yellow]")
                        self._output(f"    {item.description}")
                        self._output(f"    Wert: {item.value} Gold")
                else:
                    self._output(f"\nDie Kiste ist leer.")
            else:
                self._output(
                    f"\nDu musst die Kiste erst öffnen, um den Inhalt zu sehen."
                )
            self._output(f"[bold]{'=' * 50}[/bold]")
        else:
            self._output(f"\n{response.message}", "error")

    def _print_room(self, room: dungeon_pb2.RoomInfo):
        """Gibt Raum-Information formatiert aus"""
        self._output(f"\n[bold]{'=' * 60}[/bold]")
        self._output(f"[bold green]📍 {room.name}[/bold green]")
        self._output(f"[bold]{'=' * 60}[/bold]")
        self._output(f"{room.description}")
        self._output("")

        if room.exits:
            self._output(f"🚪 Ausgänge: [cyan]{', '.join(room.exits)}[/cyan]")
            self._update_status(exits=list(room.exits), room_name=room.name)

        if room.items:
            self._output(f"\n💎 Items im Raum:")
            for item in room.items:
                self._output(f"  - [yellow]{item.name}[/yellow]: {item.description}")

        if room.chests:
            self._output(f"\n📦 Kisten im Raum:")
            for chest in room.chests:
                status = "🔓 offen" if chest.is_open else "🔒 geschlossen"
                item_count = f" ({len(chest.items)} Items)" if chest.is_open else ""
                self._output(f"  - [cyan]{chest.name}[/cyan] [{status}]{item_count}")
                self._output(f"    {chest.description}")

        if room.npcs:
            self._output(f"\n👤 NPCs:")
            for npc in room.npcs:
                hostile = "⚔️ FEINDLICH" if npc.is_hostile else "🤝 Friedlich"
                self._output(
                    f"  - [red if npc.is_hostile else green]{npc.name}[/] [{hostile}]"
                )
                self._output(
                    f"    {npc.description} (HP: {npc.health}, MP: {npc.magic})"
                )

        if room.players:
            other_players = [p for p in room.players if p != self.player_name]
            if other_players:
                self._output(
                    f"\n👥 Andere Spieler: [yellow]{', '.join(other_players)}[/yellow]"
                )

        self._output(f"[bold]{'=' * 60}[/bold]\n")

    async def _stream_events(self):
        """Empfängt und verarbeitet Game Events"""
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
                    if event_type == "DIRECT_MESSAGE":
                        self._output(f"\n💬 {event.message}", "message")
                    elif event_type == "ROOM_MESSAGE":
                        self._output(f"\n💭 {event.message}", "message")
                    elif event_type == "BROADCAST_MESSAGE":
                        self._output(f"\n📢 {event.message}", "broadcast")
                else:
                    self._output(f"\n🔔 EVENT: {event.message}", "event")
        except asyncio.CancelledError:
            logger.info("Event Stream gestoppt")
        except Exception as e:
            if not self.stop_events.is_set():
                logger.error(f"Event Stream Fehler: {e}")

    async def _update_player_info(self):
        """Aktualisiert Spieler-Information"""
        if not self.stub or not self.player_id:
            return

        try:
            request = dungeon_pb2.GetPlayerInfoRequest(player_id=self.player_id)
            response = await self.stub.GetPlayerInfo(request)

            # Extrahiere Item-Namen aus dem Inventar
            inventory_items = [item.name for item in response.inventory]

            self._update_status(
                health=response.health,
                magic=response.magic,
                inventory_items=inventory_items,
            )
        except Exception as e:
            logger.error(f"Fehler beim Aktualisieren der Spieler-Info: {e}")


class PasswordModal(ModalScreen):
    """Modal-Dialog zur Passwort-Eingabe"""

    CSS = """
    PasswordModal {
        align: center middle;
    }

    #password-dialog {
        width: 50;
        height: auto;
        padding: 1 2;
        border: solid yellow;
        background: $surface;
    }

    #password-label {
        margin-bottom: 1;
    }

    #password-input {
        width: 100%;
        margin-bottom: 1;
    }
    """

    def __init__(self, player_name: str) -> None:
        super().__init__()
        self.player_name = player_name

    def compose(self) -> ComposeResult:
        with Container(id="password-dialog"):
            yield Label(f"Passwort für '{self.player_name}':", id="password-label")
            yield Input(
                password=True, id="password-input", placeholder="Passwort eingeben..."
            )

    def on_input_submitted(self, event: Input.Submitted) -> None:
        """Bestätigt das Passwort bei Enter"""
        event.stop()
        self.dismiss(event.value)

    def on_key(self, event) -> None:
        """Schließt Modal bei Escape ohne Ergebnis"""
        if event.key == "escape":
            self.dismiss(None)


class DungeonTextualApp(App):
    """Hauptanwendung für den Dungeon Client mit Textual"""

    CSS = """
    #main-container {
        layout: horizontal;
        height: 100%;
    }

    #left-panel {
        width: 75%;
        layout: vertical;
        border: solid green;
    }

    #right-panel {
        width: 25%;
        layout: vertical;
        border: solid cyan;
        height: 100%;
    }

    #status {
        height: 20%;
        padding: 1;
        border: solid yellow;
        background: $boost;
    }

    #inventory {
        height: 45%;
        padding: 1;
        overflow-y: auto;
        border: solid magenta;
        background: $surface;
    }

    #navigation {
        height: 35%;
        padding: 1;
        border: solid green;
        background: $boost;
    }

    #output-container {
        height: 1fr;
        border: solid green;
        padding: 1;
    }

    #nav-container {
        padding: 1;
    }

    #nav-title {
        text-align: center;
        text-style: bold;
        margin-bottom: 1;
    }

    .nav-spacer {
        width: 1fr;
    }

    #nav-row-1, #nav-row-2, #nav-row-3 {
        height: auto;
        align: center middle;
    }

    Button {
        width: 13;
        min-width: 10;
        margin: 0 1;
    }

    #input-container {
        height: auto;
        min-height: 5;
        border: solid yellow;
        padding: 1;
    }

    Input {
        width: 100%;
    }

    RichLog {
        height: 100%;
        scrollbar-gutter: stable;
    }

    Footer {
        column-span: 2;
    }
    """

    BINDINGS = [
        Binding("ctrl+c", "quit", "Beenden", priority=True),
        Binding("ctrl+l", "clear_output", "Clear"),
        Binding("right", "app.bell", "Suggestion: →", show=False),
        Binding("tab", "focus_next", "Nächstes Feld", show=False),
        Binding("shift+tab", "focus_previous", "Vorheriges Feld", show=False),
    ]

    def __init__(self):
        super().__init__()
        self.client = DungeonClient()
        self.command_history = []
        self.history_index = -1
        self.current_input = ""  # Speichert aktuelle Eingabe beim Navigieren
        self.suggester = HistorySuggester(self)  # Erstelle Suggester-Instanz

    def compose(self) -> ComposeResult:
        """Erstellt das UI Layout"""
        yield Header()

        # Hauptcontainer mit horizontalem Layout
        with Container(id="main-container"):
            # Linke Seite: Output + Input
            with Vertical(id="left-panel"):
                # Output Bereich
                with Container(id="output-container"):
                    yield RichLog(id="output", highlight=True, markup=True)

                # Input Bereich
                with Container(id="input-container"):
                    yield Input(
                        placeholder="Befehl eingeben (join <name> zum Start – Passwort wird abgefragt, help für Hilfe)...",
                        id="input",
                        suggester=self.suggester,
                    )

            # Rechte Seite: Status & Inventar & Navigation
            with Vertical(id="right-panel"):
                yield StatusPanel(id="status")
                yield InventoryPanel(id="inventory")
                yield NavigationPanel(id="navigation")

        yield Footer()

    async def on_mount(self) -> None:
        """Wird beim Start der App aufgerufen"""
        self.title = "Multi-User Dungeon"
        self.sub_title = "Textual Client"

        # Setze Callbacks
        self.client.set_output_callback(self.append_output)
        self.client.set_status_callback(self.update_status)

        # Fokussiere Input-Feld
        input_widget = self.query_one("#input", Input)
        input_widget.focus()

        # Verbinde mit Server
        output = self.query_one("#output", RichLog)
        output.write("[bold cyan]=== Multi-User Dungeon Client ===[/bold cyan]")
        output.write("Verbinde mit Server...")

        try:
            await self.client.connect()
            output.write("[green]✓ Verbunden![/green]")
            output.write(
                "\nGib [yellow]'join <dein_name>'[/yellow] ein, um zu beginnen."
            )
            output.write(
                "Gib [yellow]'help'[/yellow] ein für eine Liste aller Befehle.\n"
            )

            # Starte automatische Status-Aktualisierung alle 2 Sekunden
            self.set_interval(2.0, self.auto_update_status)
        except Exception as e:
            output.write(f"[red]✗ Fehler beim Verbinden: {e}[/red]")

    async def auto_update_status(self) -> None:
        """Aktualisiert Status automatisch alle 2 Sekunden"""
        if self.client.player_id:
            try:
                await self.client._update_player_info()
            except Exception as e:
                logger.error(f"Fehler bei automatischer Status-Aktualisierung: {e}")

    def append_output(self, text: str, style: str = ""):
        """Fügt Text zum Output hinzu"""
        output = self.query_one("#output", RichLog)

        # Konvertiere style zu Rich markup wenn nötig
        if style == "error":
            text = f"[red]{text}[/red]"
        elif style == "success":
            text = f"[green]{text}[/green]"
        elif style == "info":
            text = f"[cyan]{text}[/cyan]"
        elif style == "combat":
            text = f"[red bold]{text}[/red bold]"
        elif style == "magic":
            text = f"[magenta]{text}[/magenta]"
        elif style == "npc":
            text = f"[yellow]{text}[/yellow]"
        elif style == "message":
            text = f"[blue]{text}[/blue]"
        elif style == "broadcast":
            text = f"[bold yellow]{text}[/bold yellow]"
        elif style == "event":
            text = f"[dim]{text}[/dim]"

        output.write(text)

    def update_status(self, **kwargs):
        """Aktualisiert Status-Anzeige"""
        status = self.query_one("#status", StatusPanel)
        inventory = self.query_one("#inventory", InventoryPanel)

        if "player_name" in kwargs:
            status.player_name = kwargs["player_name"]
        if "health" in kwargs:
            status.health = kwargs["health"]
        if "magic" in kwargs:
            status.magic = kwargs["magic"]
        if "room_name" in kwargs:
            status.room_name = kwargs["room_name"]
        if "inventory_items" in kwargs:
            inventory.inventory_items = kwargs["inventory_items"]
        if "exits" in kwargs:
            nav = self.query_one("#navigation", NavigationPanel)
            nav.available_exits = kwargs["exits"]

    async def on_input_submitted(self, event: Input.Submitted) -> None:
        """Wird aufgerufen wenn Enter im Input-Feld gedrückt wird"""
        command = event.value.strip()

        if not command:
            return

        # Leere Input-Feld
        input_widget = self.query_one("#input", Input)
        input_widget.value = ""

        # Zeige Command im Output
        output = self.query_one("#output", RichLog)
        output.write(f"[bold green]>[/bold green] {command}")

        # Füge zur History hinzu
        if not self.command_history or self.command_history[-1] != command:
            self.command_history.append(command)
        self.history_index = len(self.command_history)

        # Verarbeite Command
        await self.process_command(command)

    async def on_key(self, event) -> None:
        """Handler für Tastatur-Events (für History-Navigation)"""
        input_widget = self.query_one("#input", Input)

        # Nur verarbeiten wenn Input fokussiert ist
        if not input_widget.has_focus:
            return

        if event.key == "up":
            # Pfeil hoch - zurück in der Historie
            if self.command_history:
                # Speichere aktuelle Eingabe beim ersten Pfeil hoch
                if self.history_index == len(self.command_history):
                    self.current_input = input_widget.value

                if self.history_index > 0:
                    self.history_index -= 1
                    input_widget.value = self.command_history[self.history_index]
            event.prevent_default()

        elif event.key == "down":
            # Pfeil runter - vorwärts in der Historie
            if self.command_history:
                if self.history_index < len(self.command_history) - 1:
                    self.history_index += 1
                    input_widget.value = self.command_history[self.history_index]
                elif self.history_index == len(self.command_history) - 1:
                    # Am Ende der Historie - zeige gespeicherte aktuelle Eingabe
                    self.history_index = len(self.command_history)
                    input_widget.value = self.current_input
            event.prevent_default()

    async def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handler für Button-Klicks"""
        button_id = event.button.id

        if button_id == "btn-north":
            await self.client.move("north")
        elif button_id == "btn-south":
            await self.client.move("south")
        elif button_id == "btn-east":
            await self.client.move("east")
        elif button_id == "btn-west":
            await self.client.move("west")
        elif button_id == "btn-look":
            await self.client.look_around()

    @work
    async def join_with_password(self, player_name: str) -> None:
        """Fragt Passwort per Modal ab und registriert den Spieler.
        Muss als Worker laufen, damit push_screen_wait erlaubt ist.
        """
        password = await self.app.push_screen_wait(PasswordModal(player_name))
        if not password:
            self.append_output("Anmeldung abgebrochen.", "warning")
            return
        await self.client.register(player_name, password)
        # Nach Join automatisch Look ausführen
        await self.client.look_around()

    async def process_command(self, command: str):
        """Verarbeitet einen Command"""
        parts = command.split(maxsplit=1)
        if not parts:
            return

        cmd = parts[0].lower()
        arg = parts[1] if len(parts) > 1 else ""

        try:
            if cmd == "quit" or cmd == "exit":
                await self.action_quit()
            elif cmd == "join" and arg:
                self.join_with_password(arg)
            elif cmd == "move" and arg:
                await self.client.move(arg)
            elif cmd == "look":
                await self.client.look_around()
            elif cmd == "take" and arg:
                await self.client.take_item(arg)
            elif cmd == "drop" and arg:
                await self.client.drop_item(arg)
            elif cmd == "open" and arg:
                await self.client.open_chest(arg)
            elif cmd == "close" and arg:
                await self.client.close_chest(arg)
            elif cmd in ["inspect", "untersuche", "betrachte"] and arg:
                await self.client.inspect_chest(arg)
            elif cmd == "put" and arg:
                put_parts = arg.split(maxsplit=1)
                if len(put_parts) == 2:
                    await self.client.put_in_chest(put_parts[0], put_parts[1])
                else:
                    self.append_output("Verwendung: put <item> <kiste>", "error")
            elif cmd == "get" and arg:
                get_parts = arg.split(maxsplit=1)
                if len(get_parts) == 2:
                    await self.client.get_from_chest(get_parts[0], get_parts[1])
                else:
                    self.append_output("Verwendung: get <item> <kiste>", "error")
            elif cmd == "talk" and arg:
                await self.client.talk_to_npc(arg)
            elif cmd == "attack" and arg:
                await self.client.attack_npc(arg)
            elif cmd == "info":
                await self.client.get_player_info()
            elif cmd == "read" and arg:
                await self.client.read_scroll(arg)
            elif cmd == "cast" and arg:
                cast_parts = arg.split(maxsplit=1)
                spell_name = cast_parts[0]
                target_id = cast_parts[1] if len(cast_parts) > 1 else ""
                await self.client.cast_spell(spell_name, target_id)
            elif cmd in ["spellbook", "spells"]:
                await self.client.list_spellbook()
            elif cmd == "msg" and arg:
                msg_parts = arg.split(maxsplit=1)
                if len(msg_parts) == 2:
                    await self.client.send_direct_message(msg_parts[0], msg_parts[1])
                else:
                    self.append_output(
                        "Verwendung: msg <spielername> <nachricht>", "error"
                    )
            elif cmd == "say" and arg:
                await self.client.send_room_message(arg)
            elif cmd == "shout" and arg:
                await self.client.send_broadcast_message(arg)
            elif cmd == "who":
                await self.client.get_online_players()
            elif cmd == "clear":
                await self.action_clear_output()
            elif cmd == "help":
                self.show_help()
            else:
                self.append_output(
                    f"Unbekanntes Kommando: '{cmd}'. Nutze 'help' für Hilfe.", "error"
                )
        except Exception as e:
            self.append_output(f"Fehler: {str(e)}", "error")
            logger.error(f"Kommando-Fehler: {e}", exc_info=True)

    def show_help(self):
        """Zeigt Hilfe"""
        help_text = """[bold cyan]=== Kommandos ===[/bold cyan]
[yellow]move <direction>[/yellow]        - Bewege dich (north, south, east, west)
[yellow]look[/yellow]                    - Schau dich um
[yellow]take <item>[/yellow]             - Nimm Item auf (z.B. take fackel oder take fackel 2)
[yellow]drop <item>[/yellow]             - Lege Item ab
[yellow]open <chest>[/yellow]            - Öffne Kiste (z.B. open holzkiste)
[yellow]close <chest>[/yellow]           - Schließe Kiste
[yellow]inspect <x>[/yellow]             - Untersuche Kiste
[yellow]put <item> <chest>[/yellow]      - Lege Item in Kiste
[yellow]get <item> <chest>[/yellow]      - Hole Item aus Kiste
[yellow]talk <npc_id>[/yellow]           - Sprich mit NPC
[yellow]attack <npc_id>[/yellow]         - Greife NPC an
[yellow]info[/yellow]                    - Zeige Spieler-Info
[yellow]read <rolle>[/yellow]            - Lese Zauberspruchrolle
[yellow]cast <zauber> [ziel][/yellow]    - Wirke Zauberspruch
[yellow]spellbook/spells[/yellow]        - Zeige Zauberbuch
[yellow]msg <name> <text>[/yellow]       - Direkte Nachricht
[yellow]say <text>[/yellow]              - Nachricht an Raum
[yellow]shout <text>[/yellow]            - Broadcast an alle
[yellow]who[/yellow]                     - Zeige Online-Spieler
[yellow]clear[/yellow]                   - Leere Output
[yellow]help[/yellow]                    - Zeige Kommandos
[yellow]quit/exit[/yellow]               - Beende Client
"""
        self.append_output(help_text)

    async def action_clear_output(self) -> None:
        """Leert den Output-Bereich"""
        output = self.query_one("#output", RichLog)
        output.clear()

    async def action_quit(self) -> None:
        """Beendet die Anwendung"""
        await self.client.disconnect()
        self.exit()


async def main():
    """Hauptfunktion"""
    app = DungeonTextualApp()
    await app.run_async()


def cli_main():
    """Entry point für den Client"""
    asyncio.run(main())


if __name__ == "__main__":
    cli_main()
