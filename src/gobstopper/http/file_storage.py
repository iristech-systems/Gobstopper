"""File upload handling for Gobstopper framework.

Flask/Quart-style FileStorage class for handling uploaded files from
multipart/form-data requests.
"""

import os
from pathlib import Path
from typing import BinaryIO, Optional


class FileStorage:
    """Uploaded file wrapper with convenient save/read methods.

    Flask/Quart-compatible file upload handler that wraps uploaded file data
    from multipart/form-data requests. Provides methods for saving, reading,
    and streaming file contents.

    Args:
        file: File-like object or bytes containing file data
        filename: Original filename from upload (may be None)
        name: Form field name
        content_type: MIME type from Content-Type header
        headers: Additional headers from multipart section

    Attributes:
        filename (str): Original filename from client
        name (str): Form field name
        content_type (str): MIME type
        headers (dict): Multipart section headers

    Examples:
        Save uploaded file:

        >>> @app.post('/upload')
        >>> async def upload(request):
        ...     file = request.files.get('avatar')
        ...     if file and file.filename:
        ...         # Save to uploads directory
        ...         file.save(f'uploads/{file.filename}')
        ...         return {"uploaded": file.filename}
        ...     return {"error": "No file uploaded"}, 400

        Read file contents:

        >>> @app.post('/process')
        >>> async def process(request):
        ...     file = request.files.get('data')
        ...     if file:
        ...         contents = file.read()
        ...         # Process contents...
        ...         return {"size": len(contents)}

        Save with secure filename:

        >>> from werkzeug.utils import secure_filename
        >>>
        >>> @app.post('/upload')
        >>> async def upload(request):
        ...     file = request.files.get('document')
        ...     if file and file.filename:
        ...         filename = secure_filename(file.filename)
        ...         file.save(f'uploads/{filename}')
        ...         return {"saved": filename}

        Stream large file:

        >>> @app.post('/upload-large')
        >>> async def upload_large(request):
        ...     file = request.files.get('video')
        ...     if file:
        ...         # Stream to disk to avoid memory issues
        ...         with open(f'uploads/{file.filename}', 'wb') as f:
        ...             chunk = file.stream.read(8192)
        ...             while chunk:
        ...                 f.write(chunk)
        ...                 chunk = file.stream.read(8192)
        ...         return {"uploaded": file.filename}

        Check file type:

        >>> @app.post('/upload-image')
        >>> async def upload_image(request):
        ...     file = request.files.get('image')
        ...     if not file:
        ...         return {"error": "No file"}, 400
        ...     if not file.content_type.startswith('image/'):
        ...         return {"error": "Not an image"}, 400
        ...     file.save(f'images/{file.filename}')
        ...     return {"uploaded": file.filename}

    Note:
        File data is stored in memory. For large files, consider streaming
        directly to disk or using temporary files.

    See Also:
        :attr:`Request.files`: Access uploaded files from request
        :func:`send_from_directory`: Serve files securely
    """

    def __init__(
        self,
        file: BinaryIO | bytes,
        filename: Optional[str] = None,
        name: Optional[str] = None,
        content_type: Optional[str] = 'application/octet-stream',
        headers: Optional[dict[str, str]] = None
    ):
        """Initialize FileStorage with file data and metadata.

        Args:
            file: File-like object or bytes with file contents
            filename: Original filename from client
            name: Form field name
            content_type: MIME type
            headers: Multipart headers
        """
        if isinstance(file, bytes):
            # Convert bytes to file-like object
            import io
            self.stream = io.BytesIO(file)
        else:
            self.stream = file

        self.filename = filename
        self.name = name
        self.content_type = content_type
        self.headers = headers or {}

    def save(self, dst: str | Path, buffer_size: int = 16384) -> None:
        """Save uploaded file to filesystem.

        Writes the file contents to the specified destination path. Creates
        parent directories if they don't exist. Uses buffered writing for
        efficiency with large files.

        Args:
            dst: Destination path (string or Path object)
            buffer_size: Size of buffer for writing (default: 16KB)

        Raises:
            IOError: If file cannot be written
            PermissionError: If lacking write permissions

        Examples:
            Save to specific path:

            >>> file.save('uploads/avatar.jpg')

            Save with Path object:

            >>> from pathlib import Path
            >>> file.save(Path('uploads') / 'document.pdf')

            Create directories if needed:

            >>> file.save('uploads/2024/01/file.txt')  # Creates dirs

        Note:
            Overwrites existing files without warning.
            Parent directories are created automatically.
            File position is reset to start after saving.
        """
        dst_path = Path(dst)

        # Create parent directories
        dst_path.parent.mkdir(parents=True, exist_ok=True)

        # Reset stream position
        self.stream.seek(0)

        # Write file
        with open(dst_path, 'wb') as f:
            while True:
                chunk = self.stream.read(buffer_size)
                if not chunk:
                    break
                f.write(chunk)

        # Reset position for potential re-reads
        self.stream.seek(0)

    def read(self, size: int = -1) -> bytes:
        """Read file contents as bytes.

        Reads the entire file or specified number of bytes. File position
        advances with each read. Use seek(0) to reset position.

        Args:
            size: Number of bytes to read (-1 for all, default)

        Returns:
            bytes: File contents

        Examples:
            Read entire file:

            >>> contents = file.read()
            >>> print(f"File size: {len(contents)} bytes")

            Read in chunks:

            >>> chunk = file.read(1024)  # Read 1KB
            >>> while chunk:
            ...     process(chunk)
            ...     chunk = file.read(1024)

            Read and decode text:

            >>> text = file.read().decode('utf-8')
            >>> lines = text.splitlines()

        Note:
            Reads data into memory. For large files, use stream property
            and read in chunks to avoid memory issues.
        """
        return self.stream.read(size)

    def seek(self, offset: int, whence: int = 0) -> int:
        """Change stream position.

        Args:
            offset: Position offset
            whence: Reference point (0=start, 1=current, 2=end)

        Returns:
            int: New absolute position

        Examples:
            Reset to start:

            >>> file.seek(0)

            Skip ahead:

            >>> file.seek(100)  # Skip first 100 bytes

            Go to end:

            >>> file.seek(0, 2)  # Seek to end
        """
        return self.stream.seek(offset, whence)

    def tell(self) -> int:
        """Get current stream position.

        Returns:
            int: Current position in bytes from start

        Examples:
            Check position:

            >>> pos = file.tell()
            >>> print(f"Read {pos} bytes so far")
        """
        return self.stream.tell()

    def close(self) -> None:
        """Close the underlying stream.

        Releases file resources. File cannot be read after closing.

        Examples:
            Manual cleanup:

            >>> file = request.files.get('upload')
            >>> try:
            ...     data = file.read()
            ...     process(data)
            ... finally:
            ...     file.close()

        Note:
            Usually not needed - files are closed automatically.
            Use context manager pattern if available in your use case.
        """
        self.stream.close()

    def __repr__(self) -> str:
        """String representation for debugging."""
        return f"<FileStorage: {self.filename or 'unnamed'} ({self.content_type})>"

    def __bool__(self) -> bool:
        """Check if file exists and has content.

        Returns:
            bool: True if file has a filename

        Examples:
            Check if file uploaded:

            >>> file = request.files.get('avatar')
            >>> if file:
            ...     file.save('uploads/avatar.jpg')
            ... else:
            ...     return {"error": "No file uploaded"}
        """
        return bool(self.filename)


def secure_filename(filename: str) -> str:
    """Make filename safe for filesystem.

    Removes dangerous characters and path separators to prevent
    directory traversal attacks. Compatible with werkzeug.utils.secure_filename.

    Args:
        filename: Original filename from client

    Returns:
        str: Sanitized filename safe for filesystem

    Examples:
        Basic sanitization:

        >>> secure_filename('../../etc/passwd')
        'etc_passwd'

        >>> secure_filename('my document.pdf')
        'my_document.pdf'

        >>> secure_filename('file<script>.txt')
        'filescript.txt'

        With upload:

        >>> @app.post('/upload')
        >>> async def upload(request):
        ...     file = request.files.get('document')
        ...     if file:
        ...         safe_name = secure_filename(file.filename)
        ...         file.save(f'uploads/{safe_name}')
        ...         return {"saved": safe_name}

    Note:
        Removes or replaces: /, \\, <, >, :, ", |, ?, *, ..
        Replaces spaces with underscores.
        Removes leading/trailing dots and whitespace.
    """
    import re

    # Remove path separators
    filename = filename.replace('/', '_').replace('\\', '_')

    # Remove dangerous characters
    filename = re.sub(r'[<>:"|?*]', '', filename)

    # Replace spaces with underscores
    filename = filename.replace(' ', '_')

    # Remove leading/trailing dots and whitespace
    filename = filename.strip('. ')

    # Remove parent directory references
    filename = filename.replace('..', '')

    # If empty after sanitization, use a default
    if not filename:
        filename = 'unnamed'

    return filename


__all__ = [
    'FileStorage',
    'secure_filename',
]
