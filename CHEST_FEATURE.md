# Kisten/Container Feature

## Übersicht
Das Spiel unterstützt jetzt Kisten (Chests) als Container für Items.

## Eigenschaften
- **Kisten können geöffnet und geschlossen werden**
- **Items können nur in geöffnete Kisten gelegt oder daraus entnommen werden**
- **Kisten sind zu schwer zum Aufnehmen** - sie bleiben immer im Raum
- **Nur Räume können Kisten enthalten**

## Verfügbare Kisten im Spiel

### Dungeon Eingang
- **Holzkiste**: Eine alte, verwitterte Holzkiste
  - Inhalt: Seil

### Schatzkammer
- **Schatztruhe**: Eine prachtvolle, mit Gold verzierte Truhe (standardmäßig geschlossen)
  - Inhalt: Diamant (1000 Gold), Diamant (800 Gold), Rubin (750 Gold)

## Befehle

### Kiste öffnen
```
open <kistenname>
```
Beispiele:
- `open holzkiste`
- `open schatztruhe`

### Kiste schließen
```
close <kistenname>
```
Beispiele:
- `close holzkiste`

### Kiste inspizieren
```
inspect <kistenname>
```
Zeigt Beschreibung, Status (offen/geschlossen) und Inhalt (nur wenn geöffnet)

### Item in Kiste legen
```
put <item> <kistenname>
```
Beispiele:
- `put fackel holzkiste`
- `put goldmünze schatztruhe`

Hinweis: Die Kiste muss geöffnet sein!

### Item aus Kiste holen
```
get <item> <kistenname>
```
Beispiele:
- `get seil holzkiste`
- `get diamant schatztruhe`
- `get diamant 2 schatztruhe` (holt den zweiten Diamanten)

Hinweis: Die Kiste muss geöffnet sein!

## Indexierte Items
Wie bei normalen Items kannst du auch in Kisten zwischen mehreren gleichnamigen Items unterscheiden:

```
get diamant 1 schatztruhe   # Holt ersten Diamanten
get diamant 2 schatztruhe   # Holt zweiten Diamanten
```

## Technische Details

### Backend (dungeon_manager.py)
- `open_chest(player_id, chest_name)` - Öffnet Kiste
- `close_chest(player_id, chest_name)` - Schließt Kiste
- `put_in_chest(player_id, item_name, chest_name)` - Item in Kiste legen
- `get_from_chest(player_id, item_name, chest_name)` - Item aus Kiste holen
- `inspect_chest(player_id, chest_name)` - Kiste untersuchen

### RPC Service (dungeon.proto)
- `OpenChest` - RPC zum Öffnen
- `CloseChest` - RPC zum Schließen
- `PutInChest` - RPC zum Item einlegen
- `GetFromChest` - RPC zum Item entnehmen
- `InspectChest` - RPC zum Inspizieren

### Client UI
- Kisten werden in der Raumbeschreibung mit 📦 Symbol angezeigt
- Status zeigt ob Kiste offen 🔓 oder geschlossen 🔒 ist
- Bei offenen Kisten wird Anzahl der Items angezeigt
- Befehle sind im `help` dokumentiert

## Events
Das System broadcasted Events für:
- `CHEST_OPENED` - Wenn jemand eine Kiste öffnet
- `CHEST_CLOSED` - Wenn jemand eine Kiste schließt
- `ITEM_PUT_IN_CHEST` - Wenn ein Item in eine Kiste gelegt wird
- `ITEM_TAKEN_FROM_CHEST` - Wenn ein Item aus einer Kiste genommen wird
