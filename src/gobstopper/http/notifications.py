"""Session-based notification system for Gobstopper framework.

Flask/Quart-style flash messages renamed to 'notifications' for semantic clarity.
Provides temporary message storage across requests using session backend.
"""

from typing import Any

# Import TYPE_CHECKING to avoid circular imports
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from .request import Request


def notification(request: 'Request', message: str, category: str = 'info'):
    """Add a notification message to the session.

    Gobstopper's equivalent to Flask's flash() function - stores temporary messages
    in the session that persist across redirects and can be displayed once.
    Messages are automatically cleared after being retrieved.

    Args:
        request: The current Request object with session
        message: Message text to display to the user
        category: Message category/type for styling. Standard categories:
            'success', 'info', 'warning', 'error', 'debug'

    Examples:
        Success notification after form submission:

        >>> @app.post('/users')
        >>> async def create_user(request):
        ...     user = await save_user()
        ...     notification(request, 'User created successfully!', 'success')
        ...     return redirect(url_for('user_list'))

        Error notification:

        >>> @app.post('/login')
        >>> async def login(request):
        ...     if not await authenticate(request):
        ...         notification(request, 'Invalid credentials', 'error')
        ...         return redirect(url_for('login_page'))
        ...     notification(request, f'Welcome back, {user.name}!', 'success')
        ...     return redirect(url_for('dashboard'))

        Multiple notifications:

        >>> @app.post('/process')
        >>> async def process(request):
        ...     notification(request, 'Processing started', 'info')
        ...     result = await do_work()
        ...     notification(request, f'Processed {result.count} items', 'success')
        ...     notification(request, 'Check the report for details', 'info')
        ...     return redirect(url_for('results'))

        Warning notification:

        >>> @app.get('/admin')
        >>> async def admin_panel(request):
        ...     if not request.session.get('is_admin'):
        ...         notification(request, 'Admin access required', 'warning')
        ...         return redirect(url_for('home'))
        ...     return await render_template('admin.html')

    Note:
        Requires SecurityMiddleware with session management enabled.
        Messages are stored in session under '_notifications' key.
        Standard Bootstrap alert classes map to categories:
        - 'success' → alert-success (green)
        - 'info' → alert-info (blue)
        - 'warning' → alert-warning (yellow)
        - 'error' → alert-danger (red)
        - 'debug' → alert-secondary (gray)

    See Also:
        :func:`get_notifications`: Retrieve and clear notification messages
        :class:`SecurityMiddleware`: Session management
    """
    if not request.session:
        # No session available - silently fail
        # Could log warning in debug mode
        return

    if '_notifications' not in request.session:
        request.session['_notifications'] = []

    request.session['_notifications'].append({
        'message': message,
        'category': category
    })


def get_notifications(
    request: 'Request',
    with_categories: bool = True,
    category_filter: list[str] | None = None
) -> list[tuple[str, str]] | list[str]:
    """Retrieve and clear notification messages from session.

    Fetches all pending notification messages from the session and removes them
    so they aren't displayed again. Typically called in base templates to show
    notifications site-wide.

    Args:
        request: The current Request object with session
        with_categories: If True, return (category, message) tuples.
            If False, return just message strings.
        category_filter: Optional list of categories to include (e.g., ['error', 'warning']).
            If None, returns all notifications.

    Returns:
        List of notifications. Format depends on with_categories:
        - with_categories=True: List of (category, message) tuples
        - with_categories=False: List of message strings

    Examples:
        In Jinja2 template (display all):

        >>> {% for category, message in get_notifications() %}
        ...   <div class="alert alert-{{ category }}">{{ message }}</div>
        >>> {% endfor %}

        In Tera template (display all):

        >>> {% for notification in get_notifications() %}
        ...   <div class="alert alert-{{ notification.0 }}">{{ notification.1 }}</div>
        >>> {% endfor %}

        Filter by category:

        >>> # Only show errors and warnings
        >>> for category, message in get_notifications(request, category_filter=['error', 'warning']):
        ...     print(f"[{category.upper()}] {message}")

        Without categories:

        >>> # Just get message strings
        >>> for message in get_notifications(request, with_categories=False):
        ...     print(message)

        In route handler:

        >>> @app.get('/notifications')
        >>> async def show_notifications(request):
        ...     notifications = get_notifications(request)
        ...     return jsonify({"notifications": [
        ...         {"category": cat, "message": msg}
        ...         for cat, msg in notifications
        ...     ]})

        Bootstrap styling:

        >>> {% for category, message in get_notifications() %}
        ...   {% set alert_class = 'alert-danger' if category == 'error' else 'alert-' ~ category %}
        ...   <div class="alert {{ alert_class }} alert-dismissible fade show" role="alert">
        ...     {{ message }}
        ...     <button type="button" class="btn-close" data-bs-dismiss="alert"></button>
        ...   </div>
        >>> {% endfor %}

    Note:
        Messages are removed from session after retrieval (one-time display).
        Returns empty list if no session or no notifications.
        Safe to call multiple times - subsequent calls return empty list.

    See Also:
        :func:`notification`: Add notification messages
        :func:`peek_notifications`: Get notifications without clearing them
    """
    if not request.session or '_notifications' not in request.session:
        return []

    notifications = request.session.pop('_notifications', [])

    # Apply category filter if provided
    if category_filter:
        notifications = [
            n for n in notifications
            if n['category'] in category_filter
        ]

    # Return in requested format
    if with_categories:
        return [(n['category'], n['message']) for n in notifications]
    else:
        return [n['message'] for n in notifications]


def peek_notifications(
    request: 'Request',
    with_categories: bool = True,
    category_filter: list[str] | None = None
) -> list[tuple[str, str]] | list[str]:
    """Get notifications without clearing them from session.

    Like get_notifications() but doesn't remove messages from session.
    Useful for checking if notifications exist without consuming them,
    or for displaying notifications in multiple places.

    Args:
        request: The current Request object with session
        with_categories: If True, return (category, message) tuples
        category_filter: Optional list of categories to include

    Returns:
        List of notifications in same format as get_notifications()

    Examples:
        Check if there are errors:

        >>> if any(cat == 'error' for cat, _ in peek_notifications(request)):
        ...     # Handle error state
        ...     pass

        Count notifications:

        >>> notification_count = len(peek_notifications(request, with_categories=False))
        >>> return {"pending_notifications": notification_count}

    Note:
        Messages remain in session after peeking.
        Use get_notifications() to retrieve and clear in one operation.

    See Also:
        :func:`get_notifications`: Retrieve and clear notifications
        :func:`notification`: Add notification messages
    """
    if not request.session or '_notifications' not in request.session:
        return []

    notifications = request.session.get('_notifications', [])

    # Apply category filter if provided
    if category_filter:
        notifications = [
            n for n in notifications
            if n['category'] in category_filter
        ]

    # Return in requested format
    if with_categories:
        return [(n['category'], n['message']) for n in notifications]
    else:
        return [n['message'] for n in notifications]


def clear_notifications(request: 'Request'):
    """Clear all notification messages from session without retrieving them.

    Useful for discarding notifications in error handlers or after certain events.

    Args:
        request: The current Request object with session

    Examples:
        Clear on logout:

        >>> @app.post('/logout')
        >>> async def logout(request):
        ...     clear_notifications(request)
        ...     request.session.clear()
        ...     return redirect(url_for('login'))

        Clear stale notifications:

        >>> @app.before_request
        >>> async def check_stale_notifications(request):
        ...     # Clear notifications older than 5 minutes
        ...     if should_clear_old_notifications(request):
        ...         clear_notifications(request)

    See Also:
        :func:`notification`: Add notification messages
        :func:`get_notifications`: Retrieve and clear notifications
    """
    if request.session and '_notifications' in request.session:
        del request.session['_notifications']


__all__ = [
    'notification',
    'get_notifications',
    'peek_notifications',
    'clear_notifications',
]
