"""
gRPC Server für das Multi-User Dungeon
"""
import asyncio
import logging
from typing import AsyncIterator
import grpc
from . import dungeon_pb2
from . import dungeon_pb2_grpc
from .dungeon_manager import DungeonManager

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class DungeonServiceServicer(dungeon_pb2_grpc.DungeonServiceServicer):
    """
    Implementierung des gRPC DungeonService
    """

    def __init__(self):
        self.dungeon_manager = DungeonManager()
        logger.info("Dungeon Service initialisiert")

    async def RegisterPlayer(
        self,
        request: dungeon_pb2.RegisterPlayerRequest,
        context: grpc.aio.ServicerContext
    ) -> dungeon_pb2.RegisterPlayerResponse:
        """Registriert einen neuen Spieler"""
        try:
            player = await self.dungeon_manager.register_player(request.player_name)
            logger.info(f"Spieler registriert: {player.name} (ID: {player.player_id})")

            return dungeon_pb2.RegisterPlayerResponse(
                player_id=player.player_id,
                message=f"Willkommen im Dungeon, {player.name}!",
                success=True
            )
        except Exception as e:
            logger.error(f"Fehler bei Spieler-Registrierung: {e}")
            return dungeon_pb2.RegisterPlayerResponse(
                player_id="",
                message=f"Fehler: {str(e)}",
                success=False
            )

    async def UnregisterPlayer(
        self,
        request: dungeon_pb2.UnregisterPlayerRequest,
        context: grpc.aio.ServicerContext
    ) -> dungeon_pb2.UnregisterPlayerResponse:
        """Meldet einen Spieler ab"""
        success, message = await self.dungeon_manager.unregister_player(request.player_id)
        logger.info(f"Spieler abgemeldet: {request.player_id} - {message}")

        return dungeon_pb2.UnregisterPlayerResponse(
            success=success,
            message=message
        )

    async def MovePlayer(
        self,
        request: dungeon_pb2.MovePlayerRequest,
        context: grpc.aio.ServicerContext
    ) -> dungeon_pb2.MovePlayerResponse:
        """Bewegt einen Spieler"""
        success, message, new_room = await self.dungeon_manager.move_player(
            request.player_id,
            request.direction
        )

        response = dungeon_pb2.MovePlayerResponse(
            success=success,
            message=message
        )

        if new_room:
            response.new_room.CopyFrom(new_room.to_proto_room())

        return response

    async def GetPlayerInfo(
        self,
        request: dungeon_pb2.GetPlayerInfoRequest,
        context: grpc.aio.ServicerContext
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
        self,
        request: dungeon_pb2.GetRoomInfoRequest,
        context: grpc.aio.ServicerContext
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
        self,
        request: dungeon_pb2.LookAroundRequest,
        context: grpc.aio.ServicerContext
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
        self,
        request: dungeon_pb2.TakeItemRequest,
        context: grpc.aio.ServicerContext
    ) -> dungeon_pb2.TakeItemResponse:
        """Spieler nimmt Item auf"""
        success, message = await self.dungeon_manager.take_item(
            request.player_id,
            request.item_id
        )

        return dungeon_pb2.TakeItemResponse(
            success=success,
            message=message
        )

    async def DropItem(
        self,
        request: dungeon_pb2.DropItemRequest,
        context: grpc.aio.ServicerContext
    ) -> dungeon_pb2.DropItemResponse:
        """Spieler legt Item ab"""
        success, message = await self.dungeon_manager.drop_item(
            request.player_id,
            request.item_id
        )

        return dungeon_pb2.DropItemResponse(
            success=success,
            message=message
        )

    async def TalkToNPC(
        self,
        request: dungeon_pb2.TalkToNPCRequest,
        context: grpc.aio.ServicerContext
    ) -> dungeon_pb2.TalkToNPCResponse:
        """Spieler spricht mit NPC"""
        success, message, npc_response = await self.dungeon_manager.talk_to_npc(
            request.player_id,
            request.npc_id
        )

        return dungeon_pb2.TalkToNPCResponse(
            success=success,
            message=message,
            npc_response=npc_response
        )

    async def AttackNPC(
        self,
        request: dungeon_pb2.AttackNPCRequest,
        context: grpc.aio.ServicerContext
    ) -> dungeon_pb2.AttackNPCResponse:
        """Spieler greift NPC an"""
        success, message, damage, health = await self.dungeon_manager.attack_npc(
            request.player_id,
            request.npc_id
        )

        return dungeon_pb2.AttackNPCResponse(
            success=success,
            message=message,
            damage_dealt=damage,
            npc_health_remaining=health
        )

    async def SendDirectMessage(
        self,
        request: dungeon_pb2.SendDirectMessageRequest,
        context: grpc.aio.ServicerContext
    ) -> dungeon_pb2.SendMessageResponse:
        """Sendet direkte Nachricht an einen Spieler"""
        success, message = await self.dungeon_manager.send_direct_message(
            request.sender_id,
            request.recipient_name,
            request.message
        )

        return dungeon_pb2.SendMessageResponse(
            success=success,
            message=message
        )

    async def SendRoomMessage(
        self,
        request: dungeon_pb2.SendRoomMessageRequest,
        context: grpc.aio.ServicerContext
    ) -> dungeon_pb2.SendMessageResponse:
        """Sendet Nachricht an alle im Raum"""
        success, message = await self.dungeon_manager.send_room_message(
            request.sender_id,
            request.message
        )

        return dungeon_pb2.SendMessageResponse(
            success=success,
            message=message
        )

    async def SendBroadcastMessage(
        self,
        request: dungeon_pb2.SendBroadcastMessageRequest,
        context: grpc.aio.ServicerContext
    ) -> dungeon_pb2.SendMessageResponse:
        """Sendet Broadcast an alle Spieler"""
        success, message = await self.dungeon_manager.send_broadcast_message(
            request.sender_id,
            request.message
        )

        return dungeon_pb2.SendMessageResponse(
            success=success,
            message=message
        )

    async def GetOnlinePlayers(
        self,
        request: dungeon_pb2.GetOnlinePlayersRequest,
        context: grpc.aio.ServicerContext
    ) -> dungeon_pb2.GetOnlinePlayersResponse:
        """Gibt Liste aller Online-Spieler zurück"""
        players_info = await self.dungeon_manager.get_online_players()

        player_statuses = []
        for name, room_name in players_info:
            player_statuses.append(dungeon_pb2.PlayerStatus(
                name=name,
                room_name=room_name,
                is_online=True
            ))

        return dungeon_pb2.GetOnlinePlayersResponse(
            players=player_statuses
        )

    async def StreamEvents(
        self,
        request: dungeon_pb2.StreamEventsRequest,
        context: grpc.aio.ServicerContext
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


async def serve(port: int = 50051):
    """Startet den gRPC Server"""
    server = grpc.aio.server()
    dungeon_pb2_grpc.add_DungeonServiceServicer_to_server(
        DungeonServiceServicer(), server
    )

    listen_addr = f"[::]:{port}"
    server.add_insecure_port(listen_addr)

    logger.info(f"Server startet auf {listen_addr}")
    await server.start()

    try:
        await server.wait_for_termination()
    except KeyboardInterrupt:
        logger.info("Server wird heruntergefahren...")
        await server.stop(5)


def main():
    """Entry point für den Server"""
    asyncio.run(serve())


if __name__ == "__main__":
    main()
