"""Multipart form data parser for file uploads.

Handles parsing of multipart/form-data requests for file uploads.
"""

import re
from typing import Dict, List
from .file_storage import FileStorage


def parse_multipart(body: bytes, content_type: str) -> tuple[Dict[str, List[str]], Dict[str, FileStorage]]:
    """Parse multipart/form-data request body.

    Extracts form fields and uploaded files from multipart encoded body.
    Returns separate dictionaries for form fields and files.

    Args:
        body: Raw request body bytes
        content_type: Content-Type header value (must include boundary)

    Returns:
        Tuple of (form_data, files):
        - form_data: Dict mapping field names to list of values
        - files: Dict mapping field names to FileStorage objects

    Examples:
        Parse in request handler:

        >>> body = await request.get_data()
        >>> content_type = request.headers.get('content-type', '')
        >>> form, files = parse_multipart(body, content_type)
        >>>
        >>> # Access form fields
        >>> title = form.get('title', [''])[0]
        >>>
        >>> # Access uploaded file
        >>> avatar = files.get('avatar')
        >>> if avatar:
        ...     avatar.save(f'uploads/{avatar.filename}')

    Note:
        Boundary is extracted from Content-Type header.
        Handles both text fields and file uploads.
        File data is loaded into memory - use streaming for large files.

    Raises:
        ValueError: If boundary not found in Content-Type header
    """
    # Extract boundary from Content-Type
    boundary_match = re.search(r'boundary=([^;]+)', content_type)
    if not boundary_match:
        raise ValueError("No boundary found in Content-Type header")

    boundary = boundary_match.group(1).strip('"')
    boundary_bytes = f'--{boundary}'.encode()
    end_boundary_bytes = f'--{boundary}--'.encode()

    form_data: Dict[str, List[str]] = {}
    files: Dict[str, FileStorage] = {}

    # Split by boundary
    parts = body.split(boundary_bytes)

    for part in parts:
        if not part or part == b'--\r\n' or part == b'--':
            continue

        # Skip empty parts and end boundary
        if part.startswith(b'--'):
            continue

        # Split headers from content
        try:
            header_end = part.index(b'\r\n\r\n')
        except ValueError:
            continue

        headers_bytes = part[:header_end]
        content = part[header_end + 4:]  # Skip \r\n\r\n

        # Remove trailing \r\n
        if content.endswith(b'\r\n'):
            content = content[:-2]

        # Parse headers
        headers_text = headers_bytes.decode('utf-8', errors='ignore')
        headers = {}
        for line in headers_text.split('\r\n'):
            if ':' in line:
                key, value = line.split(':', 1)
                headers[key.strip().lower()] = value.strip()

        # Parse Content-Disposition
        disposition = headers.get('content-disposition', '')
        if not disposition:
            continue

        # Extract field name
        name_match = re.search(r'name="([^"]+)"', disposition)
        if not name_match:
            continue

        field_name = name_match.group(1)

        # Check if it's a file upload
        filename_match = re.search(r'filename="([^"]*)"', disposition)

        if filename_match:
            # It's a file upload
            filename = filename_match.group(1)
            content_type_header = headers.get('content-type', 'application/octet-stream')

            file_storage = FileStorage(
                file=content,
                filename=filename if filename else None,
                name=field_name,
                content_type=content_type_header,
                headers=headers
            )
            files[field_name] = file_storage
        else:
            # It's a regular form field
            try:
                value = content.decode('utf-8', errors='replace')
                if field_name not in form_data:
                    form_data[field_name] = []
                form_data[field_name].append(value)
            except Exception:
                pass

    return form_data, files


__all__ = ['parse_multipart']
