# Multi-User Dungeon mit gRPC

Ein objektorientiertes Multi-User Dungeon Game mit asynchronem gRPC Client-Server-Architektur.

## Features

- **Objektorientiertes Design**: Player, Room, NPC, und Item Klassen
- **Asynchrone Kommunikation**: Vollständig async/await basiert (Server)
- **gRPC Protocol**: Effiziente Kommunikation zwischen Client und Server
- **Event Streaming**: Echtzeit-Updates über Spielereignisse
- **Multi-User Support**: Mehrere Spieler können gleichzeitig spielen
- **Chat-System**: Direkte Nachrichten, Raum-Chat und Broadcasts
- **Moderne Terminal-UI**: Zweigeteiltes Layout mit prompt-toolkit

## Installation

Das Projekt verwendet Poetry für Dependency Management:

```bash
poetry install
```

## Proto Files kompilieren

Falls die Proto-Files neu kompiliert werden müssen:

```bash
poetry run python -m grpc_tools.protoc -I./protos --python_out=./src/dungeon --grpc_python_out=./src/dungeon ./protos/dungeon.proto
sed -i '' 's/^import dungeon_pb2/from . import dungeon_pb2/' src/dungeon/dungeon_pb2_grpc.py
```

Oder als ein Befehl:

```bash
poetry run python -m grpc_tools.protoc -I./protos --python_out=./src/dungeon --grpc_python_out=./src/dungeon ./protos/dungeon.proto && sed -i '' 's/^import dungeon_pb2/from . import dungeon_pb2/' src/dungeon/dungeon_pb2_grpc.py
```

## Server starten

```bash
poetry run dungeon-server
```

Der Server läuft standardmäßig auf Port 50051.

## Client starten

In einem neuen Terminal:

```bash
poetry run dungeon-client
```

Der Client öffnet sich in einem modernen Terminal-UI mit:
- **Output-Bereich** (oben): Zeigt Spielausgaben, Events und Nachrichten
- **Input-Bereich** (unten): Für Kommandoeingabe mit Suchfunktion (Ctrl+R)
- **Info-Bar**: Tastenkombinationen

**Steuerung:**
- `Enter`: Kommando senden
- `Ctrl+C`: Client beenden
- `Ctrl+R`: Suche in Input-Historie

## Spielkommandos

### Bewegung & Exploration
- `move <direction>` - Bewege dich (north, south, east, west)
- `look` - Schau dich im aktuellen Raum um
- `info` - Zeige deine Spieler-Information

### Items & Inventar
- `take <item_id>` - Nimm ein Item auf
- `drop <item_id>` - Lege ein Item ab

### NPC Interaktion
- `talk <npc_id>` - Sprich mit einem NPC
- `attack <npc_id>` - Greife einen NPC an

### Kommunikation (NEU!)
- `msg <spielername> <nachricht>` - Sende direkte Nachricht an einen Spieler
- `say <nachricht>` - Sende Nachricht an alle im aktuellen Raum
- `shout <nachricht>` - Sende Broadcast an alle Spieler im Dungeon
- `who` - Zeige Liste aller online Spieler

### System
- `help` - Zeige alle Kommandos
- `quit` - Beende den Client

## Architektur

### Domain Models ([models.py](src/dungeon/models.py))
- **Player**: Spieler mit Inventar, Health, Position
- **Room**: Räume mit Ausgängen, Items, NPCs
- **NPC**: Non-Player Characters mit Dialogue und Combat
- **Item**: Items mit Beschreibung und Wert

### Dungeon Manager ([dungeon_manager.py](src/dungeon/dungeon_manager.py))
- Zentrale Spiellogik
- Verwaltung aller Spieler und Räume
- Event Broadcasting
- Thread-safe mit asyncio.Lock

### gRPC Server ([server.py](src/dungeon/server.py))
- Async gRPC Service Implementation
- DungeonService mit allen RPC Methods
- Event Streaming für Echtzeit-Updates

### gRPC Client ([client.py](src/dungeon/client.py))
- Moderne Terminal-UI mit prompt-toolkit
- Zweigeteiltes Layout: Output-Bereich (oben) und Input-Bereich (unten)
- Synchroner gRPC Client mit Threading für Event Stream
- SearchToolbar für Input-Suche
- Echtzeit-Updates im Output-Bereich
- Dark Theme mit Farbcodierung

### Protocol Buffers ([dungeon.proto](protos/dungeon.proto))
- Service Definition
- Message Types
- Request/Response Schemas

## Entwickelt mit

- Python 3.13+
- gRPC & Protocol Buffers
- prompt-toolkit für Terminal-UI
- Poetry für Dependency Management
- Async/Await für Server Concurrency
- Threading für Client Event Handling

## Multi-User Beispiel

1. Starte den Server in einem Terminal
2. Starte mehrere Clients in verschiedenen Terminals
3. Spieler sehen Events wenn andere Spieler den gleichen Raum betreten
4. Alle Spieler können gleichzeitig interagieren
5. **NEU**: Spieler können miteinander chatten:
   - `say Hallo!` - Nachricht an alle im gleichen Raum
   - `msg Alice Wie geht's?` - Private Nachricht an Alice
   - `shout Hilfe im Kerker!` - Nachricht an alle Spieler
   - `who` - Siehe wer online ist und wo

## Lizenz

MIT
