"""
PyQt6 GUI Client für das Multi-User Dungeon
"""

import asyncio
import logging
import sys
from typing import Optional
from datetime import datetime
from pathlib import Path
from PyQt6.QtWidgets import (
    QApplication,
    QMainWindow,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QTextEdit,
    QLineEdit,
    QPushButton,
    QLabel,
    QGroupBox,
    QGridLayout,
    QInputDialog,
)
from PyQt6.QtCore import Qt, QThread, QTimer, pyqtSignal, pyqtSlot
from PyQt6.QtGui import QFont
import grpc.aio
from . import dungeon_pb2
from . import dungeon_pb2_grpc

# Logging Setup
log_dir = Path.home() / ".dungeon" / "logs"
log_dir.mkdir(parents=True, exist_ok=True)
log_file = log_dir / f"client_gui_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler(log_file),
    ],
)
logger = logging.getLogger(__name__)


class AsyncWorker(QThread):
    """Worker Thread für asynchrone gRPC Operationen"""

    response_received = pyqtSignal(str)
    status_update = pyqtSignal(dict)

    def __init__(self):
        super().__init__()
        self.stub = None
        self.player_id = None
        self.running = False
        self.loop = None
        self.command_queue = None

    def run(self):
        """Startet Event Loop im Thread"""
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)
        self.command_queue = asyncio.Queue()
        self.loop.run_until_complete(self.async_main())

    async def async_main(self):
        """Hauptlogik für asynchrone Operationen"""
        self.running = True
        channel = grpc.aio.insecure_channel("localhost:50051")
        self.stub = dungeon_pb2_grpc.DungeonServiceStub(channel)

        while self.running:
            try:
                # Warte auf Command
                command = await asyncio.wait_for(self.command_queue.get(), timeout=0.1)
                await self.process_command(command)
            except asyncio.TimeoutError:
                continue
            except Exception as e:
                logger.error(f"Error in async_main: {e}")
                self.response_received.emit(f"Fehler: {str(e)}")

        await channel.close()

    async def process_command(self, command: str):
        """Verarbeitet einen Command"""
        try:
            # Interner Command für Status-Update
            if command == "__internal_status_update__":
                await self.update_player_info()
                return

            parts = command.strip().split(maxsplit=1)
            if not parts:
                return

            cmd = parts[0].lower()
            args = parts[1] if len(parts) > 1 else ""

            if cmd == "__join_with_password__":
                # Interner Befehl: args enthält "name\0password"
                sep = args.find("\0")
                if sep >= 0:
                    join_name = args[:sep]
                    join_password = args[sep + 1 :]
                    await self.handle_join(join_name, join_password)
                else:
                    self.response_received.emit("Interner Fehler beim Join-Befehl.")
            elif cmd == "look":
                await self.handle_look()
            elif cmd == "move":
                await self.handle_move(args)
            elif cmd == "inventory" or cmd == "inv":
                await self.handle_inventory()
            elif cmd == "take":
                await self.handle_take(args)
            elif cmd == "drop":
                await self.handle_drop(args)
            elif cmd == "open":
                await self.handle_open_chest(args)
            elif cmd == "close":
                await self.handle_close_chest(args)
            elif cmd == "inspect":
                await self.handle_inspect_chest(args)
            elif cmd == "put":
                await self.handle_put_in_chest(command)
            elif cmd == "get":
                await self.handle_get_from_chest(command)
            elif cmd == "read":
                await self.handle_read_scroll(args)
            elif cmd == "cast":
                await self.handle_cast_spell(command)
            elif cmd == "spellbook" or cmd == "spells":
                await self.handle_spellbook()
            elif cmd == "status":
                await self.handle_status()
            elif cmd == "help":
                self.show_help()
            else:
                self.response_received.emit(f"Unbekannter Befehl: {cmd}")

        except Exception as e:
            logger.error(f"Error processing command: {e}")
            self.response_received.emit(f"Fehler: {str(e)}")

    async def handle_join(self, player_name: str, password: str):
        """Spieler beitritt zum Dungeon mit Passwort-Authentifizierung"""
        if not player_name:
            self.response_received.emit("Bitte gib einen Spielernamen an: join <name>")
            return

        if not password:
            self.response_received.emit("Kein Passwort angegeben.")
            return

        request = dungeon_pb2.RegisterPlayerRequest(
            player_name=player_name, password=password
        )
        response = await self.stub.RegisterPlayer(request)

        if response.success:
            self.player_id = response.player_id
            self.response_received.emit(response.message)
            # Nach Join automatisch Look ausführen
            await self.handle_look()
        else:
            self.response_received.emit(f"Fehler: {response.message}")

    async def handle_look(self):
        """Schaut sich im Raum um"""
        if not self.player_id:
            self.response_received.emit(
                "Du musst erst dem Spiel beitreten (join <name>)"
            )
            return

        request = dungeon_pb2.LookAroundRequest(player_id=self.player_id)
        response = await self.stub.LookAround(request)

        room = response.room
        output = [f"\n{room.name}", "=" * len(room.name), room.description]

        if room.exits:
            output.append(f"\nAusgänge: {', '.join(room.exits)}")

        if room.items:
            output.append("\nItems:")
            for item in room.items:
                output.append(f"  - {item.name}: {item.description}")

        if room.chests:
            output.append("\nKisten:")
            for chest in room.chests:
                status = "offen" if chest.is_open else "geschlossen"
                output.append(f"  - {chest.name} ({status})")

        if room.npcs:
            output.append("\nNPCs:")
            for npc in room.npcs:
                output.append(f"  - {npc.name}: {npc.description}")

        if room.players:
            other_players = [p for p in room.players if p != ""]
            if other_players:
                output.append(f"\nAndere Spieler: {', '.join(other_players)}")

        self.response_received.emit("\n".join(output))
        self.update_status_from_room(room)

        # Hole auch Spieler-Informationen für Status-Update
        await self.update_player_info()

    async def handle_move(self, direction: str):
        """Bewegt Spieler in eine Richtung"""
        if not self.player_id:
            self.response_received.emit(
                "Du musst erst dem Spiel beitreten (join <name>)"
            )
            return

        if not direction:
            self.response_received.emit(
                "Bitte gib eine Richtung an: move <north|south|east|west>"
            )
            return

        request = dungeon_pb2.MovePlayerRequest(
            player_id=self.player_id, direction=direction.lower()
        )
        response = await self.stub.MovePlayer(request)

        if response.success:
            self.response_received.emit(f"\nDu gehst nach {direction}.")
            self.response_received.emit(f"\n{response.new_room.name}")
            self.response_received.emit(response.new_room.description)
            self.update_status_from_room(response.new_room)
            # Hole auch Spieler-Informationen für Status-Update
            await self.update_player_info()
        else:
            self.response_received.emit(f"Fehler: {response.message}")

    async def handle_inventory(self):
        """Zeigt Inventar"""
        if not self.player_id:
            self.response_received.emit(
                "Du musst erst dem Spiel beitreten (join <name>)"
            )
            return

        request = dungeon_pb2.GetPlayerInfoRequest(player_id=self.player_id)
        response = await self.stub.GetPlayerInfo(request)

        if response.inventory:
            output = ["\nInventar:"]
            for item in response.inventory:
                output.append(
                    f"  - {item.name}: {item.description} (Wert: {item.value})"
                )
            self.response_received.emit("\n".join(output))
        else:
            self.response_received.emit("Dein Inventar ist leer.")

    async def handle_take(self, item_name: str):
        """Nimmt Item auf"""
        if not self.player_id:
            self.response_received.emit(
                "Du musst erst dem Spiel beitreten (join <name>)"
            )
            return

        if not item_name:
            self.response_received.emit("Bitte gib einen Item-Namen an: take <item>")
            return

        request = dungeon_pb2.TakeItemRequest(
            player_id=self.player_id, item_id=item_name
        )
        response = await self.stub.TakeItem(request)

        self.response_received.emit(response.message)

    async def handle_drop(self, item_name: str):
        """Legt Item ab"""
        if not self.player_id:
            self.response_received.emit(
                "Du musst erst dem Spiel beitreten (join <name>)"
            )
            return

        if not item_name:
            self.response_received.emit("Bitte gib einen Item-Namen an: drop <item>")
            return

        request = dungeon_pb2.DropItemRequest(
            player_id=self.player_id, item_id=item_name
        )
        response = await self.stub.DropItem(request)

        self.response_received.emit(response.message)

    async def handle_open_chest(self, chest_name: str):
        """Öffnet eine Kiste"""
        if not self.player_id:
            self.response_received.emit(
                "Du musst erst dem Spiel beitreten (join <name>)"
            )
            return

        if not chest_name:
            self.response_received.emit("Bitte gib einen Kisten-Namen an: open <kiste>")
            return

        request = dungeon_pb2.OpenChestRequest(
            player_id=self.player_id, chest_name=chest_name
        )
        response = await self.stub.OpenChest(request)

        self.response_received.emit(response.message)

    async def handle_close_chest(self, chest_name: str):
        """Schließt eine Kiste"""
        if not self.player_id:
            self.response_received.emit(
                "Du musst erst dem Spiel beitreten (join <name>)"
            )
            return

        if not chest_name:
            self.response_received.emit(
                "Bitte gib einen Kisten-Namen an: close <kiste>"
            )
            return

        request = dungeon_pb2.CloseChestRequest(
            player_id=self.player_id, chest_name=chest_name
        )
        response = await self.stub.CloseChest(request)

        self.response_received.emit(response.message)

    async def handle_inspect_chest(self, chest_name: str):
        """Untersucht eine Kiste"""
        if not self.player_id:
            self.response_received.emit(
                "Du musst erst dem Spiel beitreten (join <name>)"
            )
            return

        if not chest_name:
            self.response_received.emit(
                "Bitte gib einen Kisten-Namen an: inspect <kiste>"
            )
            return

        request = dungeon_pb2.InspectChestRequest(
            player_id=self.player_id, chest_name=chest_name
        )
        response = await self.stub.InspectChest(request)

        if response.success:
            chest = response.chest
            status = "geöffnet" if chest.is_open else "geschlossen"
            output = [
                f"\n{chest.name}",
                "=" * len(chest.name),
                chest.description,
                f"Status: {status}",
            ]

            # Zeige Inhalt nur wenn Kiste geöffnet ist
            if chest.is_open:
                if chest.items:
                    output.append("\nInhalt:")
                    for item in chest.items:
                        output.append(f"  - {item.name}: {item.description}")
                else:
                    output.append("\nDie Kiste ist leer.")
            else:
                output.append(
                    "\nDie Kiste ist geschlossen. Öffne sie, um den Inhalt zu sehen."
                )

            self.response_received.emit("\n".join(output))
        else:
            self.response_received.emit(response.message)

    async def handle_put_in_chest(self, command: str):
        """Legt Item in Kiste (Format: put <item> in <chest>)"""
        if not self.player_id:
            self.response_received.emit(
                "Du musst erst dem Spiel beitreten (join <name>)"
            )
            return

        # Parse "put <item> in <chest>"
        parts = command.split(" in ", 1)
        if len(parts) != 2:
            self.response_received.emit("Bitte nutze das Format: put <item> in <kiste>")
            return

        item_part = parts[0].split(maxsplit=1)
        if len(item_part) < 2:
            self.response_received.emit("Bitte gib ein Item an: put <item> in <kiste>")
            return

        item_name = item_part[1].strip()
        chest_name = parts[1].strip()

        request = dungeon_pb2.PutInChestRequest(
            player_id=self.player_id, item_name=item_name, chest_name=chest_name
        )
        response = await self.stub.PutInChest(request)

        self.response_received.emit(response.message)

    async def handle_get_from_chest(self, command: str):
        """Nimmt Item aus Kiste (Format: get <item> from <chest>)"""
        if not self.player_id:
            self.response_received.emit(
                "Du musst erst dem Spiel beitreten (join <name>)"
            )
            return

        # Parse "get <item> from <chest>"
        parts = command.split(" from ", 1)
        if len(parts) != 2:
            self.response_received.emit(
                "Bitte nutze das Format: get <item> from <kiste>"
            )
            return

        item_part = parts[0].split(maxsplit=1)
        if len(item_part) < 2:
            self.response_received.emit(
                "Bitte gib ein Item an: get <item> from <kiste>"
            )
            return

        item_name = item_part[1].strip()
        chest_name = parts[1].strip()

        request = dungeon_pb2.GetFromChestRequest(
            player_id=self.player_id, item_name=item_name, chest_name=chest_name
        )
        response = await self.stub.GetFromChest(request)

        self.response_received.emit(response.message)

    async def handle_status(self):
        """Zeigt Spieler-Status"""
        if not self.player_id:
            self.response_received.emit(
                "Du musst erst dem Spiel beitreten (join <name>)"
            )
            return

        request = dungeon_pb2.GetPlayerInfoRequest(player_id=self.player_id)
        response = await self.stub.GetPlayerInfo(request)

        output = [
            f"\nStatus von {response.name}",
            "=" * (10 + len(response.name)),
            f"Health: {response.health}",
            f"Magic: {response.magic}",
            f"Aktueller Raum: {response.current_room_id}",
            f"Items im Inventar: {len(response.inventory)}",
        ]
        self.response_received.emit("\n".join(output))

    async def handle_read_scroll(self, item_name: str):
        """Liest eine Zauberspruchrolle"""
        if not self.player_id:
            self.response_received.emit(
                "Du musst erst dem Spiel beitreten (join <name>)"
            )
            return

        if not item_name:
            self.response_received.emit(
                "Bitte gib den Namen der Rolle an: read <rolle>"
            )
            return

        request = dungeon_pb2.ReadScrollRequest(
            player_id=self.player_id, item_name=item_name
        )
        response = await self.stub.ReadScroll(request)

        self.response_received.emit(response.message)

    async def handle_cast_spell(self, command: str):
        """Zaubert einen Spruch"""
        if not self.player_id:
            self.response_received.emit(
                "Du musst erst dem Spiel beitreten (join <name>)"
            )
            return

        # Parse: cast <spell> [target]
        parts = command.strip().split()
        if len(parts) < 2:
            self.response_received.emit("Nutzung: cast <zauber> [ziel]")
            return

        spell_name = parts[1]
        target_id = parts[2] if len(parts) > 2 else ""

        request = dungeon_pb2.CastSpellRequest(
            player_id=self.player_id, spell_name=spell_name, target_id=target_id
        )
        response = await self.stub.CastSpell(request)

        self.response_received.emit(response.message)

    async def handle_spellbook(self):
        """Zeigt Zauberbuch"""
        if not self.player_id:
            self.response_received.emit(
                "Du musst erst dem Spiel beitreten (join <name>)"
            )
            return

        request = dungeon_pb2.ListSpellbookRequest(player_id=self.player_id)
        response = await self.stub.ListSpellbook(request)

        if not response.spells:
            self.response_received.emit(
                "\nDein Zauberbuch ist leer. Finde Zauberspruchrollen um Zauber zu lernen!"
            )
            return

        output = ["\n=== Zauberbuch ==="]
        for spell in response.spells:
            output.append(f"\n{spell.name}:")
            output.append(f"  {spell.description}")
            output.append(f"  Manakosten: {spell.mana_cost}, Schaden: {spell.damage}")

        self.response_received.emit("\n".join(output))

    def show_help(self):
        """Zeigt Hilfe"""
        help_text = """
Verfügbare Befehle:
  join <name>              - Betritt das Dungeon (Passwort wird abgefragt)
  look                     - Schau dich im Raum um
  move <direction>         - Bewege dich (north, south, east, west)
  take <item>              - Nimm ein Item auf
  drop <item>              - Lege ein Item ab
  inventory / inv          - Zeige dein Inventar
  status                   - Zeige deinen Status

  Kisten-Befehle:
  open <kiste>             - Öffne eine Kiste
  close <kiste>            - Schließe eine Kiste
  inspect <kiste>          - Untersuche eine Kiste
  put <item> in <kiste>    - Lege Item in Kiste
  get <item> from <kiste>  - Nimm Item aus Kiste

  Zauber-Befehle:
  read <rolle>             - Lese eine Zauberspruchrolle
  cast <zauber> [ziel]     - Wirke einen Zauberspruch
  spellbook / spells       - Zeige dein Zauberbuch

  help                     - Zeige diese Hilfe
        """
        self.response_received.emit(help_text)

    def update_status_from_room(self, room_info):
        """Aktualisiert Status basierend auf Rauminformationen"""
        status = {
            "room_name": room_info.name,
            "exits": list(room_info.exits),
            "items": len(room_info.items),
            "npcs": len(room_info.npcs),
            "players": len([p for p in room_info.players if p]),
        }
        self.status_update.emit(status)

    async def update_player_info(self):
        """Holt aktuelle Spielerinformationen und aktualisiert Status"""
        if not self.player_id:
            return

        try:
            request = dungeon_pb2.GetPlayerInfoRequest(player_id=self.player_id)
            response = await self.stub.GetPlayerInfo(request)

            # Erstelle Inventar-String (nur Item-Namen)
            inventory_items = [item.name for item in response.inventory]
            inventory_str = ", ".join(inventory_items) if inventory_items else "leer"

            player_status = {
                "health": response.health,
                "magic": response.magic,
                "inventory": inventory_str,
            }
            self.status_update.emit(player_status)
        except Exception as e:
            logger.error(f"Error updating player info: {e}")

    def add_command(self, command: str):
        """Fügt Command zur Queue hinzu"""
        if self.loop and self.command_queue:
            asyncio.run_coroutine_threadsafe(self.command_queue.put(command), self.loop)

    async def unregister_player(self):
        """Meldet Spieler vom Server ab"""
        if self.stub and self.player_id:
            try:
                request = dungeon_pb2.UnregisterPlayerRequest(player_id=self.player_id)
                response = await self.stub.UnregisterPlayer(request)
                logger.info(f"Spieler abgemeldet: {response.message}")
            except Exception as e:
                logger.error(f"Fehler beim Abmelden: {e}")

    def stop(self):
        """Stoppt den Worker"""
        # Versuche Spieler abzumelden bevor wir stoppen
        if self.loop and self.player_id:
            try:
                future = asyncio.run_coroutine_threadsafe(
                    self.unregister_player(), self.loop
                )
                future.result(timeout=2.0)  # Warte max 2 Sekunden
            except Exception as e:
                logger.error(f"Fehler beim Abmelden in stop(): {e}")
        self.running = False


class DungeonGUIClient(QMainWindow):
    """Hauptfenster für den Dungeon GUI Client"""

    def __init__(self):
        super().__init__()
        self.worker = None
        self.current_exits = []
        self.command_history = []  # Befehlshistorie
        self.history_index = -1  # Aktueller Index in der Historie
        self.current_input = ""  # Aktueller Eingabetext
        self.init_ui()
        self.start_worker()

        # Timer für automatische Status-Aktualisierung (jede Sekunde)
        self.status_timer = QTimer()
        self.status_timer.timeout.connect(self.request_status_update)
        self.status_timer.start(1000)  # 1000ms = 1 Sekunde

    def init_ui(self):
        """Initialisiert die Benutzeroberfläche"""
        self.setWindowTitle("Multi-User Dungeon")
        self.setGeometry(100, 100, 900, 700)

        # Zentrales Widget
        central_widget = QWidget()
        self.setCentralWidget(central_widget)

        # Hauptlayout
        main_layout = QVBoxLayout()
        central_widget.setLayout(main_layout)

        # Ausgabebereich
        output_group = QGroupBox("Ausgabe")
        output_layout = QVBoxLayout()
        self.output_text = QTextEdit()
        self.output_text.setReadOnly(True)
        # Verwende Monospace-Font
        font = QFont()
        font.setStyleHint(QFont.StyleHint.Monospace)
        font.setPointSize(10)
        self.output_text.setFont(font)
        output_layout.addWidget(self.output_text)
        output_group.setLayout(output_layout)
        main_layout.addWidget(output_group, stretch=3)

        # Statusbereich
        status_group = QGroupBox("Status")
        status_layout = QGridLayout()

        self.room_label = QLabel("Raum: -")
        self.room_label.setFont(QFont("Arial", 10, QFont.Weight.Bold))
        status_layout.addWidget(QLabel("Aktueller Raum:"), 0, 0)
        status_layout.addWidget(self.room_label, 0, 1)

        self.health_label = QLabel("HP: -")
        status_layout.addWidget(QLabel("Lebenspunkte:"), 1, 0)
        status_layout.addWidget(self.health_label, 1, 1)

        self.magic_label = QLabel("MP: -")
        status_layout.addWidget(QLabel("Magiepunkte:"), 2, 0)
        status_layout.addWidget(self.magic_label, 2, 1)

        self.inventory_label = QLabel("Inventar: -")
        status_layout.addWidget(QLabel("Inventar:"), 3, 0)
        status_layout.addWidget(self.inventory_label, 3, 1)

        status_group.setLayout(status_layout)
        main_layout.addWidget(status_group, stretch=1)

        # Navigation - Buttons für Himmelsrichtungen
        nav_group = QGroupBox("Navigation")
        nav_layout = QGridLayout()

        self.north_button = QPushButton("⬆ Nord")
        self.north_button.clicked.connect(lambda: self.move_direction("north"))
        self.north_button.setEnabled(False)
        nav_layout.addWidget(self.north_button, 0, 1)

        self.west_button = QPushButton("⬅ West")
        self.west_button.clicked.connect(lambda: self.move_direction("west"))
        self.west_button.setEnabled(False)
        nav_layout.addWidget(self.west_button, 1, 0)

        self.east_button = QPushButton("➡ Ost")
        self.east_button.clicked.connect(lambda: self.move_direction("east"))
        self.east_button.setEnabled(False)
        nav_layout.addWidget(self.east_button, 1, 2)

        self.south_button = QPushButton("⬇ Süd")
        self.south_button.clicked.connect(lambda: self.move_direction("south"))
        self.south_button.setEnabled(False)
        nav_layout.addWidget(self.south_button, 2, 1)

        # Look Button in der Mitte
        self.look_button = QPushButton("👁 Umschauen")
        self.look_button.clicked.connect(self.look_around)
        nav_layout.addWidget(self.look_button, 1, 1)

        nav_group.setLayout(nav_layout)
        main_layout.addWidget(nav_group, stretch=1)

        # Eingabebereich
        input_group = QGroupBox("Eingabe")
        input_layout = QHBoxLayout()

        self.input_field = QLineEdit()
        self.input_field.setPlaceholderText(
            "Befehl eingeben (z.B. join <name> – Passwort wird abgefragt, help)..."
        )
        self.input_field.returnPressed.connect(self.send_command)
        self.input_field.installEventFilter(
            self
        )  # Installiere Event Filter für Tastatur-Events
        input_layout.addWidget(self.input_field)

        self.send_button = QPushButton("Senden")
        self.send_button.clicked.connect(self.send_command)
        input_layout.addWidget(self.send_button)

        self.quit_button = QPushButton("Beenden")
        self.quit_button.clicked.connect(self.close)
        input_layout.addWidget(self.quit_button)

        input_group.setLayout(input_layout)
        main_layout.addWidget(input_group, stretch=0)

        # Willkommensnachricht
        self.append_output("Willkommen im Multi-User Dungeon!")
        self.append_output("Gib 'join <dein_name>' ein, um zu beginnen.")
        self.append_output("Gib 'help' ein für eine Liste aller Befehle.\n")

    def start_worker(self):
        """Startet den Async Worker Thread"""
        self.worker = AsyncWorker()
        self.worker.response_received.connect(self.on_response_received)
        self.worker.status_update.connect(self.on_status_update)
        self.worker.start()

    @pyqtSlot(str)
    def on_response_received(self, message: str):
        """Callback wenn Antwort vom Server empfangen wurde"""
        self.append_output(message)

    @pyqtSlot(dict)
    def on_status_update(self, status: dict):
        """Callback wenn Status aktualisiert wurde"""
        if "room_name" in status:
            self.room_label.setText(status.get("room_name", "-"))
        if "health" in status:
            self.health_label.setText(f"HP: {status.get('health', 0)}")
        if "magic" in status:
            self.magic_label.setText(f"MP: {status.get('magic', 0)}")
        if "inventory" in status:
            self.inventory_label.setText(status.get("inventory", "leer"))

        # Aktualisiere verfügbare Exits
        if "exits" in status:
            self.current_exits = status.get("exits", [])
            self.update_navigation_buttons()

    def request_status_update(self):
        """Fordert Status-Aktualisierung vom Worker an"""
        if self.worker:
            self.worker.add_command("__internal_status_update__")

    def update_navigation_buttons(self):
        """Aktiviert/Deaktiviert Navigation Buttons basierend auf verfügbaren Exits"""
        self.north_button.setEnabled("north" in self.current_exits)
        self.south_button.setEnabled("south" in self.current_exits)
        self.east_button.setEnabled("east" in self.current_exits)
        self.west_button.setEnabled("west" in self.current_exits)

    def eventFilter(self, obj, event):
        """Event Filter für Eingabefeld - fängt Pfeil-hoch/runter ab"""
        from PyQt6.QtCore import QEvent
        from PyQt6.QtGui import QKeyEvent

        if obj == self.input_field and event.type() == QEvent.Type.KeyPress:
            key_event = event

            # Pfeil hoch - gehe zurück in der Historie
            if key_event.key() == Qt.Key.Key_Up:
                if self.command_history:
                    # Speichere aktuelle Eingabe beim ersten Pfeil hoch
                    if self.history_index == len(self.command_history):
                        self.current_input = self.input_field.text()

                    if self.history_index > 0:
                        self.history_index -= 1
                        self.input_field.setText(
                            self.command_history[self.history_index]
                        )
                return True

            # Pfeil runter - gehe vorwärts in der Historie
            elif key_event.key() == Qt.Key.Key_Down:
                if self.command_history:
                    if self.history_index < len(self.command_history) - 1:
                        self.history_index += 1
                        self.input_field.setText(
                            self.command_history[self.history_index]
                        )
                    elif self.history_index == len(self.command_history) - 1:
                        # Am Ende der Historie - zeige gespeicherte aktuelle Eingabe
                        self.history_index = len(self.command_history)
                        self.input_field.setText(self.current_input)
                return True

        # Standard Event Handling
        return super().eventFilter(obj, event)

    def send_command(self):
        """Sendet Command an Server"""
        command = self.input_field.text().strip()
        if not command:
            return

        self.append_output(f"> {command}")

        # Füge Command zur Historie hinzu (nur wenn nicht leer und nicht duplikat des letzten Befehls)
        if not self.command_history or self.command_history[-1] != command:
            self.command_history.append(command)

        # Reset History-Index
        self.history_index = len(self.command_history)
        self.current_input = ""

        self.input_field.clear()

        # join-Befehl: Passwort im GUI-Thread abfragen
        parts = command.split(maxsplit=1)
        if parts[0].lower() == "join":
            player_name = parts[1].strip() if len(parts) > 1 else ""
            if not player_name:
                self.append_output("Verwendung: join <spielername>")
                return

            password, ok = QInputDialog.getText(
                self,
                "Login",
                f"Passwort für '{player_name}':",
                QLineEdit.EchoMode.Password,
            )
            if not ok or not password:
                self.append_output("Anmeldung abgebrochen.")
                return

            if self.worker:
                # Passwort über internen Befehl an Worker übergeben
                self.worker.add_command(
                    f"__join_with_password__ {player_name}\0{password}"
                )
            return

        if self.worker:
            self.worker.add_command(command)

    def move_direction(self, direction: str):
        """Bewegt Spieler in angegebene Richtung"""
        if self.worker:
            self.worker.add_command(f"move {direction}")

    def look_around(self):
        """Schaut sich um"""
        if self.worker:
            self.worker.add_command("look")

    def append_output(self, text: str):
        """Fügt Text zum Ausgabebereich hinzu"""
        self.output_text.append(text)
        # Scrolle zum Ende
        scrollbar = self.output_text.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())

    def closeEvent(self, event):
        """Wird aufgerufen wenn Fenster geschlossen wird"""
        self.status_timer.stop()
        if self.worker:
            # Worker stoppen (meldet Spieler automatisch ab)
            self.worker.stop()
            # Warte kurz darauf dass der Worker ordentlich beendet
            self.worker.wait(1000)  # Max 1 Sekunde warten
        event.accept()


def main():
    """Hauptfunktion"""
    app = QApplication(sys.argv)
    window = DungeonGUIClient()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
