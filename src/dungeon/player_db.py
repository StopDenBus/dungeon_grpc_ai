"""
SQLite-Datenbank für Spieler-Persistenz mit bcrypt-Passwort-Hashing.
Datenbankpfad: ~/.dungeon/players.db
"""

import json
import sqlite3
import logging
from pathlib import Path
from typing import Optional, List, TYPE_CHECKING
import bcrypt

if TYPE_CHECKING:
    from .models import Item

logger = logging.getLogger(__name__)

# Datenbankpfad
DB_DIR = Path.home() / ".dungeon"
DB_PATH = DB_DIR / "players.db"


def _get_connection() -> sqlite3.Connection:
    """Erstellt und gibt eine Datenbankverbindung zurück."""
    DB_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn


def initialize_db() -> None:
    """Erstellt die Datenbanktabellen, falls sie noch nicht existieren."""
    with _get_connection() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS players (
                player_name TEXT PRIMARY KEY,
                password_hash TEXT NOT NULL
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS player_inventory (
                player_name TEXT NOT NULL,
                item_id     TEXT NOT NULL,
                name        TEXT NOT NULL,
                description TEXT NOT NULL,
                value       INTEGER NOT NULL,
                item_type   TEXT NOT NULL DEFAULT 'normal',
                spell_name  TEXT NOT NULL DEFAULT '',
                extra_data  TEXT NOT NULL DEFAULT '{}',
                PRIMARY KEY (player_name, item_id),
                FOREIGN KEY (player_name) REFERENCES players(player_name)
            )
        """)
        # Rückwärtskompatibilität: Spalte zu bestehenden DBs hinzufügen
        try:
            conn.execute(
                "ALTER TABLE player_inventory ADD COLUMN extra_data TEXT NOT NULL DEFAULT '{}'"
            )
        except sqlite3.OperationalError:
            pass  # Spalte existiert bereits
        conn.commit()
    logger.info(f"Datenbank initialisiert: {DB_PATH}")


def find_player(player_name: str) -> Optional[str]:
    """
    Sucht einen Spieler in der Datenbank.

    Returns:
        Den gespeicherten password_hash wenn der Spieler existiert, sonst None.
    """
    with _get_connection() as conn:
        row = conn.execute(
            "SELECT password_hash FROM players WHERE player_name = ?", (player_name,)
        ).fetchone()
    return row["password_hash"] if row else None


def create_player(player_name: str, password: str) -> str:
    """
    Legt einen neuen Spieler in der Datenbank an.
    Das Passwort wird mit bcrypt gehasht und gesalzen gespeichert.

    Returns:
        Den generierten password_hash.

    Raises:
        ValueError: Wenn der Spieler bereits existiert.
    """
    if find_player(player_name):
        raise ValueError(f"Spieler '{player_name}' existiert bereits.")

    password_hash = bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode(
        "utf-8"
    )

    with _get_connection() as conn:
        conn.execute(
            "INSERT INTO players (player_name, password_hash) VALUES (?, ?)",
            (player_name, password_hash),
        )
        conn.commit()

    logger.info(f"Neuer Spieler angelegt: '{player_name}'")
    return password_hash


def verify_password(player_name: str, password: str) -> bool:
    """
    Überprüft das Passwort eines bestehenden Spielers.

    Returns:
        True wenn Passwort korrekt, False sonst (inkl. Spieler nicht gefunden).
    """
    stored_hash = find_player(player_name)
    if stored_hash is None:
        return False
    return bcrypt.checkpw(password.encode("utf-8"), stored_hash.encode("utf-8"))


def save_inventory(player_name: str, items: List["Item"]) -> None:
    """
    Speichert das Inventar eines Spielers in der Datenbank.
    Bestehende Einträge werden vollständig ersetzt.

    Jedes Item wird über seine to_dict()-Methode serialisiert. Typ-spezifische
    Felder (z.B. damage bei Weapon) landen automatisch in der extra_data-Spalte
    als JSON — player_db.py muss für neue Item-Subklassen nie geändert werden.
    """
    with _get_connection() as conn:
        conn.execute(
            "DELETE FROM player_inventory WHERE player_name = ?", (player_name,)
        )
        for item in items:
            d = item.to_dict()
            conn.execute(
                """INSERT INTO player_inventory
                   (player_name, item_id, name, description, value, item_type, spell_name, extra_data)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    player_name,
                    d["item_id"],
                    d["name"],
                    d["description"],
                    d["value"],
                    d["item_type"],
                    d["spell_name"],
                    json.dumps(d["extra_data"]),
                ),
            )
        conn.commit()
    logger.info(f"Inventar von '{player_name}' gespeichert ({len(items)} Item(s)).")


def load_inventory(player_name: str) -> List["Item"]:
    """
    Lädt das gespeicherte Inventar eines Spielers aus der Datenbank.

    Der korrekte Python-Typ wird automatisch über Item._registry ermittelt:
    Jede Subklasse, die mit `class Foo(Item, item_type="foo")` definiert ist,
    registriert sich selbst und wird hier ohne weiteren Code korrekt
    rekonstruiert.

    Returns:
        Liste von Item-Objekten (oder Subklassen-Instanzen), kann leer sein.
    """
    from .models import Item  # Import zieht alle Subklassen mit → Registry befüllt

    with _get_connection() as conn:
        rows = conn.execute(
            """SELECT item_id, name, description, value, item_type, spell_name, extra_data
               FROM player_inventory
               WHERE player_name = ?""",
            (player_name,),
        ).fetchall()

    result = []
    for row in rows:
        cls = Item._registry.get(row["item_type"], Item)
        data = {
            "item_id": row["item_id"],
            "name": row["name"],
            "description": row["description"],
            "value": row["value"],
            "item_type": row["item_type"],
            "spell_name": row["spell_name"],
            "extra_data": json.loads(row["extra_data"] or "{}"),
        }
        result.append(cls.from_dict(data))

    logger.info(f"Inventar von '{player_name}' geladen ({len(result)} Item(s)).")
    return result
