"""
gRPC Server für das Multi-User Dungeon
"""

import asyncio
import logging
import signal
from typing import AsyncIterator
from datetime import datetime
from pathlib import Path
import grpc
from . import dungeon_pb2
from . import dungeon_pb2_grpc
from .dungeon_manager import DungeonManager
from .player_db import (
    initialize_db,
    find_player,
    create_player,
    verify_password,
    save_inventory,
    load_inventory,
)

# Logging Setup - schreibt in Datei
log_dir = Path.home() / ".dungeon" / "logs"
log_dir.mkdir(parents=True, exist_ok=True)
log_file = log_dir / f"server_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[logging.FileHandler(log_file), logging.StreamHandler()],
)
logger = logging.getLogger(__name__)
logger.info(f"Server logging to: {log_file}")


class DungeonServiceServicer(dungeon_pb2_grpc.DungeonServiceServicer):
    """
    Implementierung des gRPC DungeonService
    """

    def __init__(self):
        self.dungeon_manager = DungeonManager()
        initialize_db()
        logger.info("Dungeon Service initialisiert")

    async def RegisterPlayer(
        self,
        request: dungeon_pb2.RegisterPlayerRequest,
        context: grpc.aio.ServicerContext,
    ) -> dungeon_pb2.RegisterPlayerResponse:
        """Registriert einen Spieler oder meldet einen bestehenden an.

        - Spieler noch nicht in DB: Passwort hashen, in DB speichern, Spieler anlegen.
        - Spieler in DB vorhanden: Passwort prüfen, bei Erfolg Spieler anlegen.
        """
        player_name = request.player_name
        password = request.password

        if not player_name or not player_name.strip():
            return dungeon_pb2.RegisterPlayerResponse(
                player_id="", message="Spielername darf nicht leer sein.", success=False
            )

        if not password:
            return dungeon_pb2.RegisterPlayerResponse(
                player_id="", message="Passwort darf nicht leer sein.", success=False
            )

        try:
            existing_hash = find_player(player_name)

            if existing_hash is None:
                # Neuer Spieler: in DB anlegen
                create_player(player_name, password)
                logger.info(f"Neuer Spieler in DB gespeichert: '{player_name}'")
                welcome_msg = (
                    f"Willkommen im Dungeon, {player_name}! Dein Konto wurde erstellt."
                )
            else:
                # Bestehender Spieler: Passwort prüfen
                if not verify_password(player_name, password):
                    logger.warning(f"Falsches Passwort für Spieler '{player_name}'")
                    return dungeon_pb2.RegisterPlayerResponse(
                        player_id="", message="Falsches Passwort.", success=False
                    )
                welcome_msg = f"Willkommen zurück im Dungeon, {player_name}!"

            player = await self.dungeon_manager.register_player(player_name)
            logger.info(f"Spieler angemeldet: {player.name} (ID: {player.player_id})")

            # Inventar aus DB laden (nur für bestehende Spieler)
            if existing_hash is not None:
                saved_items = load_inventory(player_name)
                if saved_items:
                    player.inventory = saved_items
                    logger.info(
                        f"Inventar für '{player_name}' wiederhergestellt: "
                        f"{[item.name for item in saved_items]}"
                    )

            return dungeon_pb2.RegisterPlayerResponse(
                player_id=player.player_id, message=welcome_msg, success=True
            )
        except Exception as e:
            logger.error(f"Fehler bei Spieler-Registrierung: {e}")
            return dungeon_pb2.RegisterPlayerResponse(
                player_id="", message=f"Fehler: {str(e)}", success=False
            )
        except Exception as e:
            logger.error(f"Fehler bei Spieler-Registrierung: {e}")
            return dungeon_pb2.RegisterPlayerResponse(
                player_id="", message=f"Fehler: {str(e)}", success=False
            )

    async def UnregisterPlayer(
        self,
        request: dungeon_pb2.UnregisterPlayerRequest,
        context: grpc.aio.ServicerContext,
    ) -> dungeon_pb2.UnregisterPlayerResponse:
        """Meldet einen Spieler ab und speichert sein Inventar."""
        # Inventar speichern, bevor der Spieler entfernt wird
        player = await self.dungeon_manager.get_player(request.player_id)
        if player:
            save_inventory(player.name, player.inventory)
            logger.info(
                f"Inventar von '{player.name}' beim Ausloggen gespeichert: "
                f"{[item.name for item in player.inventory]}"
            )

        success, message = await self.dungeon_manager.unregister_player(
            request.player_id
        )
        logger.info(f"Spieler abgemeldet: {request.player_id} - {message}")

        return dungeon_pb2.UnregisterPlayerResponse(success=success, message=message)

    async def MovePlayer(
        self, request: dungeon_pb2.MovePlayerRequest, context: grpc.aio.ServicerContext
    ) -> dungeon_pb2.MovePlayerResponse:
        """Bewegt einen Spieler"""
        success, message, new_room = await self.dungeon_manager.move_player(
            request.player_id, request.direction
        )

        response = dungeon_pb2.MovePlayerResponse(success=success, message=message)

        if new_room:
            response.new_room.CopyFrom(new_room.to_proto_room())

        return response

    async def GetPlayerInfo(
        self,
        request: dungeon_pb2.GetPlayerInfoRequest,
        context: grpc.aio.ServicerContext,
    ) -> dungeon_pb2.PlayerInfo:
        """Gibt Spieler-Information zurück"""
        player = await self.dungeon_manager.get_player(request.player_id)

        if player:
            return player.to_proto_player()
        else:
            context.set_code(grpc.StatusCode.NOT_FOUND)
            context.set_details("Spieler nicht gefunden")
            return dungeon_pb2.PlayerInfo()

    async def GetRoomInfo(
        self, request: dungeon_pb2.GetRoomInfoRequest, context: grpc.aio.ServicerContext
    ) -> dungeon_pb2.RoomInfo:
        """Gibt Raum-Information zurück"""
        player = await self.dungeon_manager.get_player(request.player_id)

        if player and player.current_room:
            return player.current_room.to_proto_room()
        else:
            context.set_code(grpc.StatusCode.NOT_FOUND)
            context.set_details("Spieler oder Raum nicht gefunden")
            return dungeon_pb2.RoomInfo()

    async def LookAround(
        self, request: dungeon_pb2.LookAroundRequest, context: grpc.aio.ServicerContext
    ) -> dungeon_pb2.LookAroundResponse:
        """Spieler schaut sich um"""
        player = await self.dungeon_manager.get_player(request.player_id)

        if player and player.current_room:
            return dungeon_pb2.LookAroundResponse(
                room=player.current_room.to_proto_room()
            )
        else:
            context.set_code(grpc.StatusCode.NOT_FOUND)
            context.set_details("Spieler oder Raum nicht gefunden")
            return dungeon_pb2.LookAroundResponse()

    async def TakeItem(
        self, request: dungeon_pb2.TakeItemRequest, context: grpc.aio.ServicerContext
    ) -> dungeon_pb2.TakeItemResponse:
        """Spieler nimmt Item auf"""
        success, message = await self.dungeon_manager.take_item(
            request.player_id, request.item_id
        )

        return dungeon_pb2.TakeItemResponse(success=success, message=message)

    async def DropItem(
        self, request: dungeon_pb2.DropItemRequest, context: grpc.aio.ServicerContext
    ) -> dungeon_pb2.DropItemResponse:
        """Spieler legt Item ab"""
        success, message = await self.dungeon_manager.drop_item(
            request.player_id, request.item_id
        )

        return dungeon_pb2.DropItemResponse(success=success, message=message)

    async def TalkToNPC(
        self, request: dungeon_pb2.TalkToNPCRequest, context: grpc.aio.ServicerContext
    ) -> dungeon_pb2.TalkToNPCResponse:
        """Spieler spricht mit NPC"""
        success, message, npc_response = await self.dungeon_manager.talk_to_npc(
            request.player_id, request.npc_id
        )

        return dungeon_pb2.TalkToNPCResponse(
            success=success, message=message, npc_response=npc_response
        )

    async def AttackNPC(
        self, request: dungeon_pb2.AttackNPCRequest, context: grpc.aio.ServicerContext
    ) -> dungeon_pb2.AttackNPCResponse:
        """Spieler greift NPC an"""
        success, message, damage, health = await self.dungeon_manager.attack_npc(
            request.player_id, request.npc_id
        )

        return dungeon_pb2.AttackNPCResponse(
            success=success,
            message=message,
            damage_dealt=damage,
            npc_health_remaining=health,
        )

    async def SendDirectMessage(
        self,
        request: dungeon_pb2.SendDirectMessageRequest,
        context: grpc.aio.ServicerContext,
    ) -> dungeon_pb2.SendMessageResponse:
        """Sendet direkte Nachricht an einen Spieler"""
        success, message = await self.dungeon_manager.send_direct_message(
            request.sender_id, request.recipient_name, request.message
        )

        return dungeon_pb2.SendMessageResponse(success=success, message=message)

    async def SendRoomMessage(
        self,
        request: dungeon_pb2.SendRoomMessageRequest,
        context: grpc.aio.ServicerContext,
    ) -> dungeon_pb2.SendMessageResponse:
        """Sendet Nachricht an alle im Raum"""
        success, message = await self.dungeon_manager.send_room_message(
            request.sender_id, request.message
        )

        return dungeon_pb2.SendMessageResponse(success=success, message=message)

    async def SendBroadcastMessage(
        self,
        request: dungeon_pb2.SendBroadcastMessageRequest,
        context: grpc.aio.ServicerContext,
    ) -> dungeon_pb2.SendMessageResponse:
        """Sendet Broadcast an alle Spieler"""
        success, message = await self.dungeon_manager.send_broadcast_message(
            request.sender_id, request.message
        )

        return dungeon_pb2.SendMessageResponse(success=success, message=message)

    async def GetOnlinePlayers(
        self,
        request: dungeon_pb2.GetOnlinePlayersRequest,
        context: grpc.aio.ServicerContext,
    ) -> dungeon_pb2.GetOnlinePlayersResponse:
        """Gibt Liste aller Online-Spieler zurück"""
        players_info = await self.dungeon_manager.get_online_players()

        player_statuses = []
        for name, room_name in players_info:
            player_statuses.append(
                dungeon_pb2.PlayerStatus(name=name, room_name=room_name, is_online=True)
            )

        return dungeon_pb2.GetOnlinePlayersResponse(players=player_statuses)

    async def OpenChest(
        self, request: dungeon_pb2.OpenChestRequest, context: grpc.aio.ServicerContext
    ) -> dungeon_pb2.OpenChestResponse:
        """Öffnet eine Kiste"""
        success, message = await self.dungeon_manager.open_chest(
            request.player_id, request.chest_name
        )

        return dungeon_pb2.OpenChestResponse(success=success, message=message)

    async def CloseChest(
        self, request: dungeon_pb2.CloseChestRequest, context: grpc.aio.ServicerContext
    ) -> dungeon_pb2.CloseChestResponse:
        """Schließt eine Kiste"""
        success, message = await self.dungeon_manager.close_chest(
            request.player_id, request.chest_name
        )

        return dungeon_pb2.CloseChestResponse(success=success, message=message)

    async def PutInChest(
        self, request: dungeon_pb2.PutInChestRequest, context: grpc.aio.ServicerContext
    ) -> dungeon_pb2.PutInChestResponse:
        """Legt Item in Kiste"""
        success, message = await self.dungeon_manager.put_in_chest(
            request.player_id, request.item_name, request.chest_name
        )

        return dungeon_pb2.PutInChestResponse(success=success, message=message)

    async def GetFromChest(
        self,
        request: dungeon_pb2.GetFromChestRequest,
        context: grpc.aio.ServicerContext,
    ) -> dungeon_pb2.GetFromChestResponse:
        """Holt Item aus Kiste"""
        success, message = await self.dungeon_manager.get_from_chest(
            request.player_id, request.item_name, request.chest_name
        )

        return dungeon_pb2.GetFromChestResponse(success=success, message=message)

    async def InspectChest(
        self,
        request: dungeon_pb2.InspectChestRequest,
        context: grpc.aio.ServicerContext,
    ) -> dungeon_pb2.InspectChestResponse:
        """Inspiziert eine Kiste"""
        success, message, chest = await self.dungeon_manager.inspect_chest(
            request.player_id, request.chest_name
        )

        response = dungeon_pb2.InspectChestResponse(success=success, message=message)

        # Wenn erfolgreich, füge die Kiste zur Response hinzu
        if success and chest:
            response.chest.CopyFrom(chest.to_proto_chest())

        return response

    async def ReadScroll(
        self, request: dungeon_pb2.ReadScrollRequest, context: grpc.aio.ServicerContext
    ) -> dungeon_pb2.ReadScrollResponse:
        """Liest eine Zauberspruchrolle"""
        success, message = await self.dungeon_manager.read_scroll(
            request.player_id, request.item_name
        )

        return dungeon_pb2.ReadScrollResponse(success=success, message=message)

    async def CastSpell(
        self, request: dungeon_pb2.CastSpellRequest, context: grpc.aio.ServicerContext
    ) -> dungeon_pb2.CastSpellResponse:
        """Zaubert einen Spruch"""
        success, message, damage, health = await self.dungeon_manager.cast_spell(
            request.player_id, request.spell_name, request.target_id
        )

        return dungeon_pb2.CastSpellResponse(
            success=success,
            message=message,
            damage_dealt=damage,
            target_health_remaining=health,
        )

    async def ListSpellbook(
        self,
        request: dungeon_pb2.ListSpellbookRequest,
        context: grpc.aio.ServicerContext,
    ) -> dungeon_pb2.ListSpellbookResponse:
        """Gibt Zauberbuch des Spielers zurück"""
        success, spells = await self.dungeon_manager.list_spellbook(request.player_id)

        proto_spells = []
        for spell in spells:
            proto_spells.append(
                dungeon_pb2.Spell(
                    name=spell.name,
                    description=spell.description,
                    mana_cost=spell.mana_cost,
                    damage=spell.damage,
                    effect_type=spell.effect_type,
                )
            )

        return dungeon_pb2.ListSpellbookResponse(spells=proto_spells)

    async def StreamEvents(
        self,
        request: dungeon_pb2.StreamEventsRequest,
        context: grpc.aio.ServicerContext,
    ) -> AsyncIterator[dungeon_pb2.GameEvent]:
        """Streamt Game Events an Client"""
        event_queue = await self.dungeon_manager.get_events(request.player_id)

        logger.info(f"Event Stream gestartet für Spieler {request.player_id}")

        try:
            while not context.cancelled():
                try:
                    # Warte auf nächstes Event mit Timeout
                    event = await asyncio.wait_for(event_queue.get(), timeout=1.0)
                    yield event
                except asyncio.TimeoutError:
                    # Kein Event verfügbar, weiter warten
                    continue
        except asyncio.CancelledError:
            logger.info(f"Event Stream beendet für Spieler {request.player_id}")


async def shutdown():
    """
    Wird beim Herunterfahren des Servers aufgerufen.
    Hier können Cleanup-Aufgaben durchgeführt werden.
    """
    logger.info("Shutdown-Routine wird ausgeführt...")
    # Hier können später Cleanup-Aufgaben hinzugefügt werden
    # z.B. Spieler abmelden, Heartbeats stoppen, etc.
    pass


async def serve(port: int = 50051):
    """Startet den gRPC Server"""
    server = grpc.aio.server()
    servicer = DungeonServiceServicer()
    dungeon_pb2_grpc.add_DungeonServiceServicer_to_server(servicer, server)

    listen_addr = f"[::]:{port}"
    server.add_insecure_port(listen_addr)

    logger.info(f"Server startet auf {listen_addr}")
    await server.start()

    # Signal Handler für graceful shutdown
    stop_event = asyncio.Event()

    def signal_handler(sig, frame):
        logger.info(f"Signal {sig} empfangen, fahre Server herunter...")
        stop_event.set()

    # Registriere Signal Handler
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    logger.info("Server läuft. Drücke Ctrl+C zum Beenden.")

    try:
        # Warte auf Stop-Signal
        await stop_event.wait()
    finally:
        # Führe Shutdown-Routine aus
        await shutdown()

        logger.info("Stoppe gRPC Server...")
        await server.stop(5)
        logger.info("Server wurde beendet.")


def main():
    """Entry point für den Server"""
    try:
        asyncio.run(serve())
    except KeyboardInterrupt:
        # Wird behandelt durch Signal Handler
        pass


if __name__ == "__main__":
    main()
