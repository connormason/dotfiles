"""
ntfy notifications (best effort: a notification failure never breaks linking)
"""
from __future__ import annotations

import logging
import urllib.error
import urllib.request

__all__ = [
    'MAX_BODY_BYTES',
    'Notifier',
    'truncate',
]

logger = logging.getLogger(__name__)

# ntfy rejects bodies over 4096 bytes; stay under it (same margin as roles/debian/files/nas-notify)
MAX_BODY_BYTES = 3900


def truncate(message: str, limit: int = MAX_BODY_BYTES) -> str:
    """
    Cut a message to a UTF-8 byte budget without splitting a character

    :param message: text to send
    :param limit: maximum encoded size in bytes
    :return: the message, ending in an ellipsis when it was shortened
    """
    encoded = message.encode('utf-8')
    if len(encoded) <= limit:
        return message
    ellipsis = '…'.encode()
    return encoded[: limit - len(ellipsis)].decode('utf-8', errors='ignore') + '…'


class Notifier:
    """
    Publishes to one ntfy topic; a blank URL turns every call into a no-op
    """
    def __init__(self, url: str, topic: str, token: str = '', timeout: float = 10.0) -> None:
        """
        Create a notifier

        :param url: ntfy base URL (``http://ntfy:80``); empty disables notifications
        :param topic: topic name
        :param token: optional bearer token
        :param timeout: socket timeout in seconds
        """
        self.url     = url
        self.topic   = topic
        self.token   = token
        self.timeout = timeout

    @property
    def enabled(self) -> bool:
        """
        Whether a URL is configured
        """
        return bool(self.url)

    def send(self, title: str, message: str, *, priority: str = 'default', tags: str = '') -> bool:
        """
        Publish one message

        :param title: notification title (ASCII only: it travels in an HTTP header)
        :param message: body text
        :param priority: ntfy priority name
        :param tags: comma-separated ntfy tags
        :return: True if ntfy accepted the message; False if disabled or the request failed
        """
        if not self.enabled:
            return False
        request = urllib.request.Request(  # noqa: S310 - operator-set URL
            f'{self.url}/{self.topic}',
            data=truncate(message).encode('utf-8'),
            method='POST',
        )
        request.add_header('Title', title.encode('ascii', errors='replace').decode('ascii'))
        request.add_header('Priority', priority)
        if tags:
            request.add_header('Tags', tags)
        if self.token:
            request.add_header('Authorization', f'Bearer {self.token}')
        try:
            with urllib.request.urlopen(request, timeout=self.timeout):  # noqa: S310
                return True
        except (urllib.error.URLError, TimeoutError, OSError) as e:
            logger.warning('ntfy publish failed: %s', e)
            return False
