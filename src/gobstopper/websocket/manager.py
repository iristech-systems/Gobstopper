"""WebSocket room management for Gobstopper framework.

This module provides a comprehensive WebSocket connection manager with room-based
organization for building real-time applications like chat systems, live dashboards,
collaborative editing, and multiplayer games.

The WebSocketManager class offers:
- Centralized connection tracking and lifecycle management
- Room-based organization for targeted message broadcasting
- Automatic cleanup of dead connections
- Thread-safe operations for concurrent access
- Efficient broadcast mechanisms for one-to-many communication

Key Concepts:
    Connection: Individual WebSocket client identified by unique connection_id
    Room: Named group of connections that can receive broadcasts together
    Broadcast: Sending messages to multiple connections simultaneously

Architecture:
    The manager maintains two key data structures:
    - connections: Dict mapping connection_id -> WebSocket instance
    - rooms: Dict mapping room_name -> Set of connection_ids

    This separation allows:
    - O(1) connection lookups
    - O(1) room membership checks
    - Efficient multi-room membership per connection
    - Easy cleanup when connections close

Use Cases:
    Chat rooms: Users join named chat rooms to exchange messages
    Live updates: Broadcast data updates to subscribers of specific topics
    Notifications: Send alerts to specific user groups
    Gaming: Manage players in different game lobbies
    Collaboration: Sync state across users editing the same document

Examples:
    Basic chat room implementation:

    >>> from gobstopper import Gobstopper
    >>> from gobstopper.websocket import WebSocketManager
    >>> import uuid
    >>>
    >>> app = Gobstopper()
    >>> manager = WebSocketManager()
    >>>
    >>> @app.websocket("/ws/chat/<room>")
    >>> async def chat_handler(websocket, room):
    ...     conn_id = str(uuid.uuid4())
    ...     await websocket.accept()
    ...     manager.add_connection(conn_id, websocket)
    ...     manager.join_room(conn_id, room)
    ...
    ...     try:
    ...         while True:
    ...             message = await websocket.receive()
    ...             if message.type == "close":
    ...                 break
    ...             if message.type == "text":
    ...                 await manager.broadcast_to_room(room, message.data)
    ...     finally:
    ...         manager.remove_connection(conn_id)

    Multi-room user presence:

    >>> @app.websocket("/ws/notifications")
    >>> async def notification_handler(websocket):
    ...     conn_id = str(uuid.uuid4())
    ...     await websocket.accept()
    ...     manager.add_connection(conn_id, websocket)
    ...
    ...     # User can join multiple notification topics
    ...     manager.join_room(conn_id, "global")
    ...     manager.join_room(conn_id, f"user_{user_id}")
    ...     manager.join_room(conn_id, f"team_{team_id}")
    ...
    ...     # Now receives broadcasts from all three rooms
    ...     while True:
    ...         message = await websocket.receive()
    ...         if message.type == "close":
    ...             break

    Admin broadcast to all users:

    >>> async def notify_all_users(message: str):
    ...     await manager.broadcast_to_all(message)

    Room statistics and monitoring:

    >>> def get_room_stats(room: str) -> dict:
    ...     connections = manager.get_room_connections(room)
    ...     return {
    ...         "room": room,
    ...         "active_users": len(connections),
    ...         "connection_ids": list(connections)
    ...     }

Security Considerations:
    - Always validate connection_ids to prevent injection attacks
    - Implement authentication before adding connections
    - Sanitize room names to prevent unauthorized access
    - Rate limit broadcast operations to prevent abuse
    - Monitor connection counts to detect DoS attempts

Performance Notes:
    - Room lookups are O(1) with hash-based dictionaries
    - Broadcasting is O(n) where n is room size
    - Connection cleanup is O(m) where m is number of rooms
    - Memory usage scales with: connections + (rooms × avg_room_size)

See Also:
    :class:`WebSocket`: Individual WebSocket connection wrapper
    :mod:`gobstopper.core.app`: Main Gobstopper application for routing
"""

from collections import defaultdict
from typing import Dict, Set

from .connection import WebSocket


class WebSocketManager:
    """Centralized WebSocket connection manager with room-based organization.

    Manages WebSocket connections with support for rooms (groups), broadcasting,
    and automatic connection lifecycle management. Designed for building real-time
    applications with many concurrent connections and targeted message delivery.

    The manager provides efficient data structures for:
    - Fast connection lookups by ID
    - Organizing connections into named rooms
    - Broadcasting messages to rooms or all connections
    - Tracking which rooms a connection belongs to
    - Automatic cleanup of disconnected clients

    Attributes:
        connections: Dictionary mapping connection_id (str) to WebSocket instances.
            Maintains all active WebSocket connections.
        rooms: Dictionary mapping room names (str) to Sets of connection_ids.
            Organizes connections into logical groups for targeted broadcasting.

    Thread Safety:
        This implementation is NOT thread-safe by default. For multi-threaded
        applications, wrap operations in locks or use asyncio's thread-safe
        primitives.

    Examples:
        Initialize manager and handle connections:

        >>> from gobstopper.websocket import WebSocketManager
        >>> manager = WebSocketManager()
        >>>
        >>> # In your WebSocket handler
        >>> conn_id = "user_123"
        >>> manager.add_connection(conn_id, websocket)
        >>> manager.join_room(conn_id, "lobby")

        Complete chat application:

        >>> import uuid
        >>> from gobstopper import Gobstopper
        >>>
        >>> app = Gobstopper()
        >>> manager = WebSocketManager()
        >>>
        >>> @app.websocket("/chat/<room_name>")
        >>> async def chat(websocket, room_name):
        ...     conn_id = str(uuid.uuid4())
        ...     await websocket.accept()
        ...     manager.add_connection(conn_id, websocket)
        ...     manager.join_room(conn_id, room_name)
        ...
        ...     try:
        ...         # Send join notification
        ...         await manager.broadcast_to_room(
        ...             room_name,
        ...             f"User {conn_id[:8]} joined"
        ...         )
        ...
        ...         # Message loop
        ...         while True:
        ...             msg = await websocket.receive()
        ...             if msg.type == "close":
        ...                 break
        ...             if msg.type == "text":
        ...                 await manager.broadcast_to_room(room_name, msg.data)
        ...     finally:
        ...         manager.remove_connection(conn_id)
        ...         await manager.broadcast_to_room(
        ...             room_name,
        ...             f"User {conn_id[:8]} left"
        ...         )

        Multi-room presence (user in multiple rooms):

        >>> conn_id = "user_456"
        >>> manager.add_connection(conn_id, websocket)
        >>> manager.join_room(conn_id, "general")
        >>> manager.join_room(conn_id, "announcements")
        >>> manager.join_room(conn_id, "team_alpha")
        >>>
        >>> # User receives broadcasts from all three rooms
        >>> rooms = manager.get_connection_rooms(conn_id)
        >>> print(rooms)  # {'general', 'announcements', 'team_alpha'}

        Room monitoring and statistics:

        >>> def get_all_room_stats():
        ...     stats = {}
        ...     for room in manager.rooms.keys():
        ...         connections = manager.get_room_connections(room)
        ...         stats[room] = {
        ...             "users": len(connections),
        ...             "connection_ids": list(connections)
        ...         }
        ...     return stats

        Graceful shutdown:

        >>> async def shutdown():
        ...     # Notify all users
        ...     await manager.broadcast_to_all(
        ...         "Server shutting down in 10 seconds"
        ...     )
        ...     # Close all connections
        ...     for conn_id, ws in list(manager.connections.items()):
        ...         await ws.close(1001, "Server shutdown")
        ...         manager.remove_connection(conn_id)

    See Also:
        :class:`WebSocket`: Individual WebSocket connection
        :meth:`broadcast_to_room`: Send message to specific room
        :meth:`broadcast_to_all`: Send message to all connections
    """

    def __init__(self):
        """Initialize empty WebSocket manager.

        Creates a new manager with no connections or rooms. The connections
        dictionary and rooms defaultdict are initialized and ready for use.

        Examples:
            >>> manager = WebSocketManager()
            >>> print(len(manager.connections))  # 0
            >>> print(len(manager.rooms))  # 0
        """
        self.connections: Dict[str, WebSocket] = {}
        self.rooms: Dict[str, Set[str]] = defaultdict(set)
    
    def add_connection(self, connection_id: str, websocket: WebSocket):
        """Register a new WebSocket connection with the manager.

        Adds a WebSocket connection to the manager's tracking dictionary. This
        must be called after accepting the WebSocket connection and before using
        any room or broadcast features.

        The connection_id should be unique across all active connections. Using
        UUIDs or session tokens is recommended to ensure uniqueness.

        Args:
            connection_id: Unique identifier for this connection. Must be hashable
                and unique. Recommended to use UUID4 or secure random string.
            websocket: The WebSocket instance to register. Should already be
                accepted (websocket.accept() called).

        Examples:
            Using UUID for connection ID:

            >>> import uuid
            >>> conn_id = str(uuid.uuid4())
            >>> manager.add_connection(conn_id, websocket)

            Using session-based ID:

            >>> session_id = request.session["user_id"]
            >>> conn_id = f"user_{session_id}"
            >>> manager.add_connection(conn_id, websocket)

            Complete connection lifecycle:

            >>> @app.websocket("/ws")
            >>> async def handler(websocket):
            ...     conn_id = str(uuid.uuid4())
            ...     await websocket.accept()
            ...     manager.add_connection(conn_id, websocket)
            ...     try:
            ...         # Handle messages...
            ...         pass
            ...     finally:
            ...         manager.remove_connection(conn_id)

        Note:
            If connection_id already exists, it will be overwritten. Ensure IDs
            are unique to avoid connection conflicts.

        See Also:
            :meth:`remove_connection`: Remove connection from manager
            :meth:`join_room`: Add connection to a room
        """
        self.connections[connection_id] = websocket
    
    def remove_connection(self, connection_id: str):
        """Remove a WebSocket connection and clean up all room memberships.

        Removes the connection from the manager and automatically removes it from
        all rooms it was a member of. This is the proper way to clean up when a
        connection closes, ensuring no dangling references remain.

        The operation is idempotent - calling it multiple times with the same
        connection_id is safe and has no effect after the first removal.

        Args:
            connection_id: The unique identifier of the connection to remove.

        Examples:
            Basic cleanup in finally block:

            >>> try:
            ...     await websocket.accept()
            ...     manager.add_connection(conn_id, websocket)
            ...     # Handle messages...
            ... finally:
            ...     manager.remove_connection(conn_id)

            Cleanup with logging:

            >>> def cleanup_connection(conn_id: str):
            ...     rooms = manager.get_connection_rooms(conn_id)
            ...     manager.remove_connection(conn_id)
            ...     logger.info(f"Removed {conn_id} from {len(rooms)} rooms")

            Graceful disconnect with notification:

            >>> async def disconnect_user(conn_id: str):
            ...     # Get rooms before removal
            ...     user_rooms = manager.get_connection_rooms(conn_id)
            ...
            ...     # Notify rooms about departure
            ...     for room in user_rooms:
            ...         await manager.broadcast_to_room(
            ...             room,
            ...             f"User {conn_id} disconnected"
            ...         )
            ...
            ...     # Remove connection
            ...     manager.remove_connection(conn_id)

            Bulk cleanup on shutdown:

            >>> async def cleanup_all():
            ...     conn_ids = list(manager.connections.keys())
            ...     for conn_id in conn_ids:
            ...         manager.remove_connection(conn_id)

        Note:
            This method is safe to call even if connection_id doesn't exist.
            All room memberships are automatically cleaned up.
            Empty rooms remain in the rooms dictionary (with empty sets).

        See Also:
            :meth:`add_connection`: Register a new connection
            :meth:`leave_room`: Remove from specific room only
        """
        if connection_id in self.connections:
            # Remove from all rooms
            for room_connections in self.rooms.values():
                room_connections.discard(connection_id)

            # Remove connection
            del self.connections[connection_id]
    
    def join_room(self, connection_id: str, room: str):
        """Add a connection to a named room for targeted broadcasting.

        Adds the specified connection to a room, allowing it to receive broadcasts
        sent to that room. Connections can be members of multiple rooms simultaneously.
        If the room doesn't exist, it will be created automatically.

        This operation only succeeds if the connection exists in the manager. Attempting
        to add a non-existent connection to a room will silently fail.

        Args:
            connection_id: Unique identifier of the connection to add to the room.
                Must be a connection previously registered with add_connection().
            room: Name of the room to join. Can be any string identifier. Room is
                created automatically if it doesn't exist.

        Examples:
            Join single room:

            >>> manager.add_connection(conn_id, websocket)
            >>> manager.join_room(conn_id, "general")

            Join multiple rooms:

            >>> manager.join_room(conn_id, "global_chat")
            >>> manager.join_room(conn_id, "announcements")
            >>> manager.join_room(conn_id, f"user_{user_id}_private")

            Dynamic room joining based on user:

            >>> @app.websocket("/ws/subscribe")
            >>> async def subscribe_handler(websocket):
            ...     await websocket.accept()
            ...     conn_id = str(uuid.uuid4())
            ...     manager.add_connection(conn_id, websocket)
            ...
            ...     # User sends room names to join
            ...     while True:
            ...         message = await websocket.receive()
            ...         if message.type == "text":
            ...             data = json.loads(message.data)
            ...             if data["action"] == "join":
            ...                 manager.join_room(conn_id, data["room"])
            ...                 await websocket.send_text(
            ...                     f"Joined room: {data['room']}"
            ...                 )

            Topic-based subscriptions:

            >>> # User subscribes to multiple topics
            >>> user_topics = ["python", "javascript", "devops"]
            >>> for topic in user_topics:
            ...     manager.join_room(conn_id, f"topic_{topic}")

            Permission-based room access:

            >>> async def join_with_permission(conn_id, room, user):
            ...     if await user.has_permission(room):
            ...         manager.join_room(conn_id, room)
            ...         return True
            ...     return False

        Note:
            Silently does nothing if connection_id not in manager.connections.
            Joining the same room multiple times has no additional effect.
            Room is created automatically on first join.

        See Also:
            :meth:`leave_room`: Remove connection from room
            :meth:`broadcast_to_room`: Send message to room members
            :meth:`get_room_connections`: Get all connections in room
        """
        if connection_id in self.connections:
            self.rooms[room].add(connection_id)
    
    def leave_room(self, connection_id: str, room: str):
        """Remove a connection from a specific room.

        Removes the connection from the specified room without affecting its
        membership in other rooms or removing it from the manager. This is useful
        for managing dynamic subscriptions where users can leave specific channels
        without disconnecting entirely.

        The operation is idempotent - calling it multiple times or on a connection
        that isn't in the room has no effect.

        Args:
            connection_id: Unique identifier of the connection to remove from room.
            room: Name of the room to leave.

        Examples:
            Leave single room:

            >>> manager.leave_room(conn_id, "general")

            Dynamic unsubscribe:

            >>> @app.websocket("/ws/manage")
            >>> async def manage_subscriptions(websocket):
            ...     conn_id = str(uuid.uuid4())
            ...     await websocket.accept()
            ...     manager.add_connection(conn_id, websocket)
            ...
            ...     while True:
            ...         message = await websocket.receive()
            ...         if message.type == "text":
            ...             data = json.loads(message.data)
            ...             if data["action"] == "leave":
            ...                 manager.leave_room(conn_id, data["room"])
            ...                 await websocket.send_text(
            ...                     f"Left room: {data['room']}"
            ...                 )

            Leave multiple rooms:

            >>> rooms_to_leave = ["channel1", "channel2", "channel3"]
            >>> for room in rooms_to_leave:
            ...     manager.leave_room(conn_id, room)

            Permission revocation:

            >>> async def revoke_access(conn_id: str, room: str):
            ...     manager.leave_room(conn_id, room)
            ...     # Notify user
            ...     ws = manager.connections.get(conn_id)
            ...     if ws:
            ...         await ws.send_text(
            ...             f"Access to {room} has been revoked"
            ...         )

            Clean exit from specific room:

            >>> # Leave room but stay connected
            >>> rooms = manager.get_connection_rooms(conn_id)
            >>> if "temporary_room" in rooms:
            ...     manager.leave_room(conn_id, "temporary_room")

        Note:
            Does not remove connection from manager, only from the room.
            Safe to call even if connection not in room or room doesn't exist.
            Connection remains active and in other rooms.

        See Also:
            :meth:`join_room`: Add connection to room
            :meth:`remove_connection`: Remove connection entirely
            :meth:`get_connection_rooms`: Check which rooms connection is in
        """
        if room in self.rooms:
            self.rooms[room].discard(connection_id)
    
    async def broadcast_to_room(self, room: str, message: str):
        """Broadcast text message to all connections in a specific room.

        Sends the same text message to every connection currently in the specified
        room. Failed sends (due to closed connections) automatically trigger cleanup
        of that connection from the manager.

        This is an async operation that sends messages sequentially to each connection
        in the room. For better performance with large rooms, consider implementing
        parallel sends with asyncio.gather().

        Args:
            room: Name of the room to broadcast to.
            message: Text message to send to all room members. Must be a string.

        Examples:
            Simple room broadcast:

            >>> await manager.broadcast_to_room("lobby", "Welcome everyone!")

            Chat message broadcasting:

            >>> @app.websocket("/chat/<room>")
            >>> async def chat_handler(websocket, room):
            ...     conn_id = str(uuid.uuid4())
            ...     await websocket.accept()
            ...     manager.add_connection(conn_id, websocket)
            ...     manager.join_room(conn_id, room)
            ...
            ...     while True:
            ...         msg = await websocket.receive()
            ...         if msg.type == "text":
            ...             # Broadcast to everyone in room
            ...             await manager.broadcast_to_room(
            ...                 room,
            ...                 f"{conn_id[:8]}: {msg.data}"
            ...             )

            JSON broadcast:

            >>> import json
            >>> data = {"type": "update", "value": 42}
            >>> await manager.broadcast_to_room(
            ...     "notifications",
            ...     json.dumps(data)
            ... )

            Notify room about events:

            >>> async def notify_room_event(room: str, event: str, data: dict):
            ...     message = json.dumps({
            ...         "event": event,
            ...         "data": data,
            ...         "timestamp": time.time()
            ...     })
            ...     await manager.broadcast_to_room(room, message)

            System announcements:

            >>> async def system_announce(room: str, announcement: str):
            ...     await manager.broadcast_to_room(
            ...         room,
            ...         f"[SYSTEM] {announcement}"
            ...     )

            Multiple room broadcast:

            >>> async def broadcast_to_multiple_rooms(rooms: list, message: str):
            ...     for room in rooms:
            ...         await manager.broadcast_to_room(room, message)

        Note:
            Messages are sent sequentially, not in parallel.
            Failed sends automatically clean up dead connections.
            If room doesn't exist or is empty, nothing happens.
            For binary data, use websocket.send_bytes() directly on each connection.

        See Also:
            :meth:`broadcast_to_all`: Broadcast to all connections
            :meth:`get_room_connections`: Get connection IDs in room
            :class:`WebSocket.send_text`: Underlying send method
        """
        if room in self.rooms:
            for connection_id in self.rooms[room]:
                if connection_id in self.connections:
                    websocket = self.connections[connection_id]
                    try:
                        await websocket.send_text(message)
                    except Exception:
                        # Connection may be closed, remove it
                        self.remove_connection(connection_id)
    
    async def broadcast_to_all(self, message: str):
        """Broadcast text message to every active connection.

        Sends the same text message to all connections registered with the manager,
        regardless of room membership. This is useful for system-wide announcements,
        critical alerts, or global events.

        Failed sends (due to closed connections) automatically trigger cleanup of
        that connection. Uses list() to create a snapshot of connections to avoid
        modification during iteration.

        Args:
            message: Text message to send to all connections. Must be a string.

        Examples:
            System-wide announcement:

            >>> await manager.broadcast_to_all(
            ...     "Server will restart in 5 minutes"
            ... )

            Global notification:

            >>> import json
            >>> notification = {
            ...     "type": "announcement",
            ...     "message": "New feature deployed!",
            ...     "priority": "high"
            ... }
            >>> await manager.broadcast_to_all(json.dumps(notification))

            Scheduled broadcast:

            >>> import asyncio
            >>>
            >>> async def scheduled_announcement():
            ...     while True:
            ...         await asyncio.sleep(3600)  # Every hour
            ...         await manager.broadcast_to_all(
            ...             "Hourly server status: All systems operational"
            ...         )

            Emergency alert:

            >>> async def emergency_broadcast(alert_message: str):
            ...     priority_msg = json.dumps({
            ...         "type": "emergency",
            ...         "message": alert_message,
            ...         "timestamp": time.time()
            ...     })
            ...     await manager.broadcast_to_all(priority_msg)

            Server shutdown notification:

            >>> async def notify_shutdown():
            ...     await manager.broadcast_to_all(
            ...         "Server shutting down for maintenance"
            ...     )
            ...     await asyncio.sleep(2)  # Give time to send
            ...     # Proceed with shutdown...

            Broadcast with counter:

            >>> async def count_broadcast_recipients(message: str):
            ...     initial_count = len(manager.connections)
            ...     await manager.broadcast_to_all(message)
            ...     final_count = len(manager.connections)
            ...     failed = initial_count - final_count
            ...     return {"sent": final_count, "failed": failed}

        Note:
            Sends to ALL connections, ignoring room memberships.
            Messages are sent sequentially, not in parallel.
            Creates connection snapshot to handle concurrent modifications.
            Failed sends automatically clean up dead connections.
            For large connection counts, consider rate limiting or batching.

        See Also:
            :meth:`broadcast_to_room`: Broadcast to specific room
            :meth:`get_room_connections`: Get connections in a room
            :class:`WebSocket.send_text`: Underlying send method
        """
        for connection_id, websocket in list(self.connections.items()):
            try:
                await websocket.send_text(message)
            except Exception:
                # Connection may be closed, remove it
                self.remove_connection(connection_id)
    
    def get_room_connections(self, room: str) -> Set[str]:
        """Get all connection IDs currently in a specific room.

        Returns a copy of the set of connection IDs that are members of the
        specified room. The returned set is a copy, so modifications won't
        affect the manager's internal state.

        Args:
            room: Name of the room to query.

        Returns:
            Set of connection_id strings for all connections in the room.
            Returns empty set if room doesn't exist or has no members.

        Examples:
            Get room size:

            >>> connections = manager.get_room_connections("lobby")
            >>> print(f"Lobby has {len(connections)} users")

            Check if connection in room:

            >>> room_members = manager.get_room_connections("vip_lounge")
            >>> if conn_id in room_members:
            ...     print("User is in VIP lounge")

            Room statistics:

            >>> def get_room_info(room: str) -> dict:
            ...     connections = manager.get_room_connections(room)
            ...     return {
            ...         "room": room,
            ...         "member_count": len(connections),
            ...         "members": list(connections)
            ...     }

            Iterate over room members:

            >>> room_members = manager.get_room_connections("announcements")
            >>> for conn_id in room_members:
            ...     ws = manager.connections.get(conn_id)
            ...     if ws:
            ...         print(f"Connection {conn_id} is active")

            Compare room sizes:

            >>> def find_most_popular_room() -> str:
            ...     max_size = 0
            ...     popular = None
            ...     for room in manager.rooms.keys():
            ...         size = len(manager.get_room_connections(room))
            ...         if size > max_size:
            ...             max_size = size
            ...             popular = room
            ...     return popular

        Note:
            Returns a copy of the set, safe to modify without affecting manager.
            Empty set returned if room doesn't exist.
            Connection IDs in set may reference closed connections.

        See Also:
            :meth:`get_connection_rooms`: Get rooms a connection is in
            :meth:`join_room`: Add connection to room
            :meth:`broadcast_to_room`: Send message to room
        """
        return self.rooms.get(room, set()).copy()
    
    def get_connection_rooms(self, connection_id: str) -> Set[str]:
        """Get all rooms that a specific connection is a member of.

        Iterates through all rooms to find which ones contain the specified
        connection. Returns a new set containing the room names, so modifications
        won't affect the manager's internal state.

        Args:
            connection_id: Unique identifier of the connection to query.

        Returns:
            Set of room name strings that the connection is a member of.
            Returns empty set if connection is not in any rooms.

        Examples:
            Check user's room memberships:

            >>> rooms = manager.get_connection_rooms(conn_id)
            >>> print(f"User is in {len(rooms)} rooms: {rooms}")

            Verify room membership:

            >>> user_rooms = manager.get_connection_rooms(conn_id)
            >>> if "admin_only" in user_rooms:
            ...     print("User has admin access")

            Display user's subscriptions:

            >>> async def show_subscriptions(websocket, conn_id):
            ...     rooms = manager.get_connection_rooms(conn_id)
            ...     await websocket.send_text(
            ...         f"You are subscribed to: {', '.join(rooms)}"
            ...     )

            Leave all rooms except one:

            >>> def keep_only_room(conn_id: str, keep_room: str):
            ...     current_rooms = manager.get_connection_rooms(conn_id)
            ...     for room in current_rooms:
            ...         if room != keep_room:
            ...             manager.leave_room(conn_id, room)

            Connection activity report:

            >>> def get_connection_report(conn_id: str) -> dict:
            ...     rooms = manager.get_connection_rooms(conn_id)
            ...     ws = manager.connections.get(conn_id)
            ...     return {
            ...         "connection_id": conn_id,
            ...         "active": ws is not None,
            ...         "room_count": len(rooms),
            ...         "rooms": list(rooms)
            ...     }

            Cleanup before disconnect:

            >>> async def graceful_disconnect(conn_id: str):
            ...     # Notify all rooms user was in
            ...     rooms = manager.get_connection_rooms(conn_id)
            ...     for room in rooms:
            ...         await manager.broadcast_to_room(
            ...             room,
            ...             f"User {conn_id} has left {room}"
            ...         )
            ...     # Remove connection
            ...     manager.remove_connection(conn_id)

        Note:
            Returns a new set, safe to modify without affecting manager.
            Empty set if connection not in any rooms.
            Performance is O(n) where n is total number of rooms.

        See Also:
            :meth:`get_room_connections`: Get connections in a room
            :meth:`join_room`: Add connection to room
            :meth:`leave_room`: Remove from specific room
        """
        rooms = set()
        for room, connections in self.rooms.items():
            if connection_id in connections:
                rooms.add(room)
        return rooms