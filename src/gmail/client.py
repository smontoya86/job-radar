"""Gmail API client."""
import base64
import logging
from dataclasses import dataclass
from datetime import datetime
from email.utils import parsedate_to_datetime
from typing import Optional

from googleapiclient.discovery import build

from .auth import GmailAuth

logger = logging.getLogger(__name__)


@dataclass
class EmailMessage:
    """Parsed email message."""

    id: str
    thread_id: str
    subject: str
    from_address: str
    from_name: str
    to_address: str
    date: datetime
    body_text: str
    body_html: Optional[str] = None
    snippet: str = ""
    labels: list[str] = None

    def __post_init__(self):
        if self.labels is None:
            self.labels = []


class GmailClient:
    """Gmail API client for fetching emails."""

    def __init__(self, auth: GmailAuth):
        """
        Initialize Gmail client.

        Args:
            auth: GmailAuth instance for authentication
        """
        self.auth = auth
        self._service = None

    def _get_service(self):
        """Get or create Gmail API service."""
        if self._service is None:
            credentials = self.auth.get_credentials()
            if not credentials:
                raise RuntimeError("Gmail authentication required")
            self._service = build("gmail", "v1", credentials=credentials)
        return self._service

    def search_messages(
        self,
        query: str,
        max_results: int = 100,
        after_date: Optional[datetime] = None,
        before_date: Optional[datetime] = None,
    ) -> list[str]:
        """
        Search for messages matching query.

        Args:
            query: Gmail search query (same syntax as Gmail search)
            max_results: Maximum number of message IDs to return
            after_date: Only return messages after this date
            before_date: Only return messages before this date

        Returns:
            List of message IDs
        """
        service = self._get_service()

        # Build query with date filters
        if after_date:
            query += f" after:{after_date.strftime('%Y/%m/%d')}"
        if before_date:
            query += f" before:{before_date.strftime('%Y/%m/%d')}"

        message_ids = []
        page_token = None

        while len(message_ids) < max_results:
            try:
                result = (
                    service.users()
                    .messages()
                    .list(
                        userId="me",
                        q=query,
                        maxResults=min(100, max_results - len(message_ids)),
                        pageToken=page_token,
                    )
                    .execute()
                )

                messages = result.get("messages", [])
                message_ids.extend(msg["id"] for msg in messages)

                page_token = result.get("nextPageToken")
                if not page_token:
                    break

            except Exception as e:
                logger.error("Gmail search error: %s", e)
                break

        return message_ids[:max_results]

    def get_message(self, message_id: str) -> Optional[EmailMessage]:
        """
        Get full message details.

        Args:
            message_id: Gmail message ID

        Returns:
            EmailMessage or None if not found
        """
        service = self._get_service()

        try:
            result = (
                service.users()
                .messages()
                .get(userId="me", id=message_id, format="full")
                .execute()
            )
            return self._parse_message(result)

        except Exception as e:
            logger.error("Gmail get message error: %s", e)
            return None

    def get_messages(self, message_ids: list[str]) -> list[EmailMessage]:
        """
        Get multiple messages.

        Args:
            message_ids: List of message IDs

        Returns:
            List of EmailMessage objects
        """
        messages = []
        for msg_id in message_ids:
            msg = self.get_message(msg_id)
            if msg:
                messages.append(msg)
        return messages

    def _parse_message(self, data: dict) -> EmailMessage:
        """Parse raw Gmail API response into EmailMessage."""
        headers = {h["name"].lower(): h["value"] for h in data["payload"]["headers"]}

        # Parse from address and name
        from_header = headers.get("from", "")
        from_name = ""
        from_address = from_header
        if "<" in from_header:
            from_name = from_header.split("<")[0].strip().strip('"')
            from_address = from_header.split("<")[1].rstrip(">")

        # Parse date
        date_str = headers.get("date", "")
        try:
            date = parsedate_to_datetime(date_str)
        except Exception:
            date = datetime.now()

        # Extract body
        body_text, body_html = self._extract_body(data["payload"])

        return EmailMessage(
            id=data["id"],
            thread_id=data["threadId"],
            subject=headers.get("subject", ""),
            from_address=from_address,
            from_name=from_name,
            to_address=headers.get("to", ""),
            date=date,
            body_text=body_text,
            body_html=body_html,
            snippet=data.get("snippet", ""),
            labels=data.get("labelIds", []),
        )

    def _extract_body(self, payload: dict) -> tuple[str, Optional[str]]:
        """Extract text and HTML body from message payload."""
        body_text = ""
        body_html = None

        def extract_parts(payload):
            nonlocal body_text, body_html

            mime_type = payload.get("mimeType", "")

            if "body" in payload and payload["body"].get("data"):
                data = payload["body"]["data"]
                decoded = base64.urlsafe_b64decode(data).decode("utf-8", errors="ignore")

                if mime_type == "text/plain":
                    body_text = decoded
                elif mime_type == "text/html":
                    body_html = decoded

            if "parts" in payload:
                for part in payload["parts"]:
                    extract_parts(part)

        extract_parts(payload)

        # If no plain text, try to convert HTML
        if not body_text and body_html:
            # Simple HTML to text conversion
            import re
            text = re.sub(r"<[^>]+>", " ", body_html)
            text = re.sub(r"\s+", " ", text)
            body_text = text.strip()

        return body_text, body_html

    def search_job_emails(
        self,
        after_date: Optional[datetime] = None,
        before_date: Optional[datetime] = None,
        max_results: int = 500,
        label: Optional[str] = None,
    ) -> list[str]:
        """
        Search for job-related emails.

        Args:
            after_date: Only return messages after this date
            before_date: Only return messages before this date
            max_results: Maximum number of messages
            label: Gmail label/folder to search in (e.g., "Job Posting")

        Returns:
            List of message IDs
        """
        # If a specific label is provided, just search that folder
        if label:
            # Gmail label query - use quotes for labels with spaces
            query = f'label:"{label}"'
            return self.search_messages(
                query=query,
                max_results=max_results,
                after_date=after_date,
                before_date=before_date,
            )

        # Build comprehensive query for job-related emails
        queries = [
            # Application confirmations
            '("thank you for applying" OR "application received" OR "we received your application")',
            # Rejections
            '("after careful consideration" OR "decided to move forward" OR "position has been filled")',
            # Interview invitations
            '("schedule an interview" OR "next steps" OR "meet with our team" OR calendly OR "calendar invite")',
            # General job keywords
            '(from:greenhouse OR from:lever OR from:workday OR from:icims OR from:jobvite)',
        ]

        combined_query = " OR ".join(queries)

        return self.search_messages(
            query=combined_query,
            max_results=max_results,
            after_date=after_date,
            before_date=before_date,
        )
