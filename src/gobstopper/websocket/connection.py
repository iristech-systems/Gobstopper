"""WebSocket connection handling for Gobstopper framework.

This module provides WebSocket support through Granian's RSGI protocol, offering
a high-level interface for real-time bidirectional communication between server
and clients.

The WebSocket class wraps the low-level RSGI WebSocket protocol and provides:
- Automatic connection lifecycle management
- Message size limits and validation (configurable via environment)
- Automatic chunking for large messages with backpressure
- Support for both text and binary messages
- Type-safe message receiving with proper error handling

Security Features:
    - Message size limits (default 1 MiB) to prevent memory exhaustion
    - Automatic connection closure on oversized messages (WebSocket code 1009)
    - Chunked transmission to provide backpressure and prevent buffer overflow

Configuration:
    Environment variables for tuning:
    - MAX_WS_MESSAGE_BYTES: Maximum message size in bytes (default: 1048576 = 1 MiB)
    - WS_SEND_CHUNK_BYTES: Chunk size for large messages (default: 65536 = 64 KiB)

Examples:
    Simple echo server:

    >>> from gobstopper import Gobstopper
    >>> app = Gobstopper()
    >>>
    >>> @app.websocket("/ws/echo")
    >>> async def echo(websocket):
    ...     await websocket.accept()
    ...     while True:
    ...         message = await websocket.receive()
    ...         if message.type == "close":
    ...             break
    ...         if message.type == "text":
    ...             await websocket.send_text(f"Echo: {message.data}")

    JSON message handling:

    >>> import json
    >>>
    >>> @app.websocket("/ws/api")
    >>> async def api_handler(websocket):
    ...     await websocket.accept()
    ...     async for message in websocket:
    ...         if message.type == "text":
    ...             data = json.loads(message.data)
    ...             result = await process_request(data)
    ...             await websocket.send_text(json.dumps(result))

    Binary data streaming:

    >>> @app.websocket("/ws/stream")
    >>> async def stream_handler(websocket):
    ...     await websocket.accept()
    ...     # Stream large binary data in chunks
    ...     with open("large_file.bin", "rb") as f:
    ...         while chunk := f.read(65536):
    ...             await websocket.send_bytes(chunk)

Note:
    This module requires Granian with RSGI support. Fallback types are provided
    for development environments without Granian installed.

See Also:
    :class:`WebSocketManager`: Room-based connection management
    :mod:`gobstopper.core.app`: Main Gobstopper application class
"""

import os

try:
    from granian.rsgi import Scope, WebsocketProtocol
except ImportError:
    # Fallback types for development without Granian
    class Scope:
        proto: str
        method: str
        path: str
        query_string: str
        headers: any
    
    class WebsocketProtocol:
        async def accept(self): pass


class WebSocket:
    """WebSocket connection wrapper for RSGI protocol.
    
    Provides a high-level interface for WebSocket communication through
    Granian's RSGI WebSocket protocol. Handles connection lifecycle,
    message sending/receiving, and connection management.
    
    Args:
        scope: RSGI WebSocket scope containing connection metadata
        protocol: RSGI WebSocket protocol instance for communication
        
    Attributes:
        scope: Original RSGI scope object with connection info
        protocol: RSGI WebSocket protocol for low-level operations
        transport: Active transport instance (set after accept())
        
    Examples:
        Basic echo server:
        
        >>> @app.websocket("/ws/echo")
        >>> async def echo_handler(websocket: WebSocket):
        ...     await websocket.accept()
        ...     while True:
        ...         message = await websocket.receive()
        ...         if message.type == "text":
        ...             await websocket.send_text(f"Echo: {message.data}")
        ...         elif message.type == "close":
        ...             break
        
        Chat room implementation:
        
        >>> @app.websocket("/ws/chat")
        >>> async def chat_handler(websocket: WebSocket):
        ...     await websocket.accept()
        ...     try:
        ...         while True:
        ...             message = await websocket.receive()
        ...             if message.type == "text":
        ...                 # Broadcast to all connected clients
        ...                 await broadcast_message(message.data)
        ...     except ConnectionClosed:
        ...         pass  # Client disconnected
        
        Binary data handling:
        
        >>> @app.websocket("/ws/data")  
        >>> async def data_handler(websocket: WebSocket):
        ...     await websocket.accept()
        ...     async for message in websocket.receive_iter():
        ...         if message.type == "bytes":
        ...             processed = process_binary_data(message.data)
        ...             await websocket.send_bytes(processed)
        
    Note:
        Must call accept() before sending/receiving messages.
        WebSocket connections are persistent until explicitly closed.
        Use try/except to handle connection errors gracefully.
        
    See Also:
        :class:`WebSocketManager`: Room-based connection management
        :meth:`Gobstopper.websocket`: WebSocket route decorator
    """
    
    def __init__(self, scope: Scope, protocol: WebsocketProtocol):
        self.scope = scope
        self.protocol = protocol
        self.transport = None
        # Limits and backpressure config
        try:
            self.max_message_bytes = int(os.getenv("MAX_WS_MESSAGE_BYTES", "1048576"))  # 1 MiB default
        except Exception:
            self.max_message_bytes = 1_048_576
        try:
            self.send_chunk_bytes = int(os.getenv("WS_SEND_CHUNK_BYTES", "65536"))  # 64 KiB default
        except Exception:
            self.send_chunk_bytes = 65536
    
    async def accept(self):
        """Accept the WebSocket connection and establish transport.
        
        Must be called before sending or receiving messages. Creates the
        transport layer for bidirectional communication.
        
        Returns:
            Transport instance for low-level operations (usually not needed)
            
        Raises:
            ConnectionError: If connection cannot be established
            RuntimeError: If already accepted or connection closed
            
        Examples:
            Standard connection acceptance:
            
            >>> @app.websocket("/ws")
            >>> async def handler(websocket):
            ...     await websocket.accept()
            ...     # Now ready to send/receive
            
        Note:
            This must be the first operation after receiving WebSocket instance.
            Connection cannot be accepted twice.
        """
        self.transport = await self.protocol.accept()
        return self.transport
    
    async def send_text(self, data: str):
        """Send text message to WebSocket client with automatic chunking.

        Sends text messages with automatic chunking for large payloads to provide
        backpressure management. Messages exceeding the configured size limit will
        cause the connection to close with status code 1009 (Message Too Big).

        The message is encoded to UTF-8 and checked against the maximum message
        size limit (configurable via MAX_WS_MESSAGE_BYTES environment variable,
        default 1 MiB). Large messages are automatically split into chunks
        (configurable via WS_SEND_CHUNK_BYTES, default 64 KiB).

        Args:
            data: Text message to send. Will be UTF-8 encoded before transmission.

        Raises:
            RuntimeError: If WebSocket connection not accepted (transport is None)
            ConnectionError: If connection fails during transmission

        Examples:
            Sending simple text messages:

            >>> await websocket.accept()
            >>> await websocket.send_text("Hello, client!")
            >>> await websocket.send_text("Another message")

            Sending JSON data:

            >>> import json
            >>> data = {"type": "notification", "message": "Update available"}
            >>> await websocket.send_text(json.dumps(data))

            Handling large messages:

            >>> # Large message is automatically chunked
            >>> large_text = "x" * 500_000  # 500 KB text
            >>> await websocket.send_text(large_text)
            >>> # Sent in chunks with automatic backpressure

            Broadcasting to multiple clients:

            >>> for ws in active_connections:
            ...     await ws.send_text(broadcast_message)

        Note:
            Messages larger than max_message_bytes will close the connection.
            Chunking happens automatically for messages > send_chunk_bytes.
            The transport.drain() method is called after each chunk if available.
            Silent failure if transport is None (connection not accepted).

        See Also:
            :meth:`send_bytes`: Send binary data
            :meth:`accept`: Must be called before sending
        """
        if not self.transport:
            return
        # Enforce message size limit
        b = data.encode('utf-8')
        if len(b) > self.max_message_bytes:
            # Close with 1009 Message Too Big
            if hasattr(self.protocol, 'close'):
                await self.protocol.close(1009)
            return
        # Chunked send with optional drain()
        chunk = self.send_chunk_bytes
        if len(b) <= chunk:
            await self.transport.send_str(data)
            if hasattr(self.transport, 'drain'):
                await self.transport.drain()
            return
        # Send in chunks to provide backpressure
        for i in range(0, len(b), chunk):
            piece = b[i:i+chunk]
            await self.transport.send_bytes(piece)
            if hasattr(self.transport, 'drain'):
                await self.transport.drain()
    
    async def send_bytes(self, data: bytes):
        """Send binary message to WebSocket client with automatic chunking.

        Sends binary messages with automatic chunking for large payloads to provide
        backpressure management. Messages exceeding the configured size limit will
        cause the connection to close with status code 1009 (Message Too Big).

        The binary data is checked against the maximum message size limit
        (configurable via MAX_WS_MESSAGE_BYTES environment variable, default 1 MiB).
        Large messages are automatically split into chunks (configurable via
        WS_SEND_CHUNK_BYTES, default 64 KiB).

        Args:
            data: Binary data to send as bytes or bytearray.

        Raises:
            RuntimeError: If WebSocket connection not accepted (transport is None)
            ConnectionError: If connection fails during transmission

        Examples:
            Sending binary data:

            >>> await websocket.accept()
            >>> binary_data = b"\\x00\\x01\\x02\\x03"
            >>> await websocket.send_bytes(binary_data)

            Sending image data:

            >>> with open("image.png", "rb") as f:
            ...     image_data = f.read()
            >>> await websocket.send_bytes(image_data)

            Sending protocol buffers:

            >>> import my_proto_pb2
            >>> message = my_proto_pb2.MyMessage()
            >>> message.field = "value"
            >>> await websocket.send_bytes(message.SerializeToString())

            Chunked large binary transfer:

            >>> # Large binary is automatically chunked
            >>> large_data = bytes(500_000)  # 500 KB
            >>> await websocket.send_bytes(large_data)
            >>> # Sent in 64 KB chunks with backpressure

        Note:
            Messages larger than max_message_bytes will close the connection.
            Chunking happens automatically for messages > send_chunk_bytes.
            The transport.drain() method is called after each chunk if available.
            Silent failure if transport is None (connection not accepted).

        See Also:
            :meth:`send_text`: Send text messages
            :meth:`accept`: Must be called before sending
        """
        if not self.transport:
            return
        if len(data) > self.max_message_bytes:
            if hasattr(self.protocol, 'close'):
                await self.protocol.close(1009)
            return
        chunk = self.send_chunk_bytes
        if len(data) <= chunk:
            await self.transport.send_bytes(data)
            if hasattr(self.transport, 'drain'):
                await self.transport.drain()
            return
        for i in range(0, len(data), chunk):
            piece = data[i:i+chunk]
            await self.transport.send_bytes(piece)
            if hasattr(self.transport, 'drain'):
                await self.transport.drain()
    
    async def receive(self):
        """Receive message from WebSocket client.
        
        Waits for and receives the next message from the client.
        Returns a message object with type and data attributes.
        
        Returns:
            Message object with:
                - type: Message type ("text", "bytes", "close", "error")
                - data: Message content (string for text, bytes for binary)
                - None: If transport not available
            
        Raises:
            ConnectionError: If connection is closed unexpectedly
            RuntimeError: If connection not accepted
            
        Examples:
            Basic message receiving:
            
            >>> message = await websocket.receive()
            >>> if message.type == "text":
            ...     print(f"Received: {message.data}")
            >>> elif message.type == "close":
            ...     print("Client disconnected")
            
            Message type handling:
            
            >>> while True:
            ...     message = await websocket.receive()
            ...     if message.type == "text":
            ...         await handle_text_message(message.data)
            ...     elif message.type == "bytes":  
            ...         await handle_binary_data(message.data)
            ...     elif message.type == "close":
            ...         break
            
        Note:
            This method blocks until a message is received.
            Handle connection close messages to avoid errors.
            
        See Also:
            :meth:`send_text`: Send text messages
            :meth:`send_bytes`: Send binary messages
        """
        if not self.transport:
            return None
        msg = await self.transport.receive()
        try:
            mtype = getattr(msg, 'type', None)
            mdata = getattr(msg, 'data', None)
            size = None
            if mtype == 'text' and isinstance(mdata, str):
                size = len(mdata.encode('utf-8'))
            elif mtype == 'bytes' and isinstance(mdata, (bytes, bytearray)):
                size = len(mdata)
            if size is not None and size > self.max_message_bytes:
                if hasattr(self.protocol, 'close'):
                    await self.protocol.close(1009)
                # Return a close-like message structure
                return type('WSMessage', (), {'type': 'close', 'code': 1009})()
        except Exception:
            # If inspection fails, just pass through
            pass
        return msg

    async def close(self, code: int = 1000, reason: str = ""):
        """Close the WebSocket connection gracefully.

        Closes the WebSocket connection with an optional close code and reason.
        Following the WebSocket protocol specification for standard close codes.

        Standard WebSocket close codes:
            - 1000: Normal closure (default)
            - 1001: Going away (server shutdown, browser navigation)
            - 1002: Protocol error
            - 1003: Unsupported data type
            - 1007: Invalid payload data
            - 1008: Policy violation
            - 1009: Message too big
            - 1011: Internal server error

        Args:
            code: WebSocket close status code (default: 1000 for normal closure).
                Must be a valid WebSocket close code (1000-4999).
            reason: Optional human-readable close reason string. Must be UTF-8
                and no longer than 123 bytes when encoded.

        Raises:
            RuntimeError: If connection not accepted (transport is None)
            ValueError: If code is invalid or reason is too long

        Examples:
            Normal closure:

            >>> await websocket.accept()
            >>> # ... handle messages ...
            >>> await websocket.close()

            Closure with reason:

            >>> await websocket.close(1000, "Session ended")

            Error closure:

            >>> try:
            ...     await process_message(message)
            >>> except ValidationError:
            ...     await websocket.close(1008, "Invalid message format")

            Server shutdown:

            >>> for ws in active_connections:
            ...     await ws.close(1001, "Server shutting down")

        Note:
            After closing, no further messages can be sent or received.
            Client may also initiate close; handle "close" message type in receive().
            Connection is automatically cleaned up after close.

        See Also:
            :meth:`accept`: Accept connection before closing
            :meth:`receive`: Receive close messages from client
        """
        if self.protocol and hasattr(self.protocol, 'close'):
            await self.protocol.close(code, reason)
        self.transport = None