from __future__ import annotations

from abc import ABC, abstractmethod


class EmailProvider(ABC):
    @abstractmethod
    def send(
        self,
        *,
        to_email: str,
        subject: str,
        text_body: str,
        html_body: str | None = None,
    ) -> str | None:
        """Send an email and return a provider message identifier when available."""
