import base64
import json
import uuid
from email.mime.text import MIMEText
from typing import Any, Dict, List, Optional

from app.config import GOOGLE_CREDENTIALS_FILE, GOOGLE_TOKEN_FILE, GMAIL_OAUTH_REDIRECT_URI
from app.schemas import AuditLog, Message

GMAIL_SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.send",
    "https://www.googleapis.com/auth/gmail.modify",
]


class GmailService:
    def __init__(self) -> None:
        self._service: Any = None

    def _build_service(self) -> Any:
        import os
        from google.oauth2.credentials import Credentials
        from googleapiclient.discovery import build

        # Prefer GMAIL_TOKEN_JSON env var (Docker/cloud deployments).
        # Fall back to token file for local dev.
        token_json = os.environ.get("GMAIL_TOKEN_JSON", "")
        if token_json:
            creds = Credentials.from_authorized_user_info(
                __import__("json").loads(token_json), GMAIL_SCOPES
            )
        else:
            creds = Credentials.from_authorized_user_file(GOOGLE_TOKEN_FILE, GMAIL_SCOPES)

        if not creds.valid:
            if creds.expired and creds.refresh_token:
                from google.auth.transport.requests import Request
                creds.refresh(Request())
                self._save_token(creds)
            else:
                raise RuntimeError(
                    "Gmail token invalid or missing. Complete OAuth2 flow at /oauth/start."
                )
        return build("gmail", "v1", credentials=creds)

    def _get_service(self) -> Any:
        if self._service is None:
            self._service = self._build_service()
        return self._service

    @staticmethod
    def _save_token(creds: Any) -> None:
        import os
        os.makedirs("config", exist_ok=True)
        with open(GOOGLE_TOKEN_FILE, "w") as f:
            f.write(creds.to_json())

    @staticmethod
    def get_oauth_flow() -> Any:
        from google_auth_oauthlib.flow import Flow
        flow = Flow.from_client_secrets_file(
            GOOGLE_CREDENTIALS_FILE,
            scopes=GMAIL_SCOPES,
            redirect_uri=GMAIL_OAUTH_REDIRECT_URI,
        )
        return flow

    @staticmethod
    async def get_oauth_url() -> str:
        flow = GmailService.get_oauth_flow()
        auth_url, _ = flow.authorization_url(prompt="consent", access_type="offline")
        return auth_url

    @staticmethod
    async def complete_oauth(code: str) -> None:
        flow = GmailService.get_oauth_flow()
        flow.fetch_token(code=code)
        GmailService._save_token(flow.credentials)
        await AuditLog.append("oauth_completed", {"service": "gmail"})

    async def poll_messages(
        self, label: str = "INBOX", max_results: int = 10
    ) -> List[Message]:
        await AuditLog.append("poll_messages", {"service": "gmail", "label": label})
        service = self._get_service()

        result = (
            service.users()
            .messages()
            .list(userId="me", labelIds=[label], maxResults=max_results)
            .execute()
        )

        messages: List[Message] = []
        for msg_ref in result.get("messages", []):
            raw = (
                service.users()
                .messages()
                .get(userId="me", id=msg_ref["id"], format="full")
                .execute()
            )
            parsed = self._parse_message(raw)
            if parsed:
                messages.append(parsed)

        return messages

    def _parse_message(self, raw: Dict[str, Any]) -> Optional[Message]:
        headers = {
            h["name"].lower(): h["value"]
            for h in raw.get("payload", {}).get("headers", [])
        }
        subject = headers.get("subject", "")
        from_header = headers.get("from", "")

        # Extract plain email address from "Name <email>" format
        if "<" in from_header:
            sender_email = from_header.split("<")[-1].rstrip(">").strip().lower()
        else:
            sender_email = from_header.strip().lower()

        body = self._extract_body(raw.get("payload", {}))

        return Message(
            id=str(uuid.uuid4()),
            sender_email=sender_email,
            subject=subject,
            body=body,
            message_id=raw["id"],
        )

    async def fetch_message(self, message_id: str) -> Optional[Message]:
        """Fetch a single Gmail message by ID."""
        await AuditLog.append("fetch_message", {"message_id": message_id})
        try:
            service = self._get_service()
            raw = (
                service.users()
                .messages()
                .get(userId="me", id=message_id, format="full")
                .execute()
            )
            return self._parse_message(raw)
        except Exception as e:
            await AuditLog.append("fetch_message_failed", {
                "message_id": message_id,
                "error": str(e),
            })
            return None

    async def list_new_messages(self, history_id: str) -> List[Message]:
        """
        Use the Gmail history API to find messages added since history_id.
        Gmail Pub/Sub notifications carry a historyId, not a message ID.
        """
        await AuditLog.append("list_new_messages", {"history_id": history_id})
        messages: List[Message] = []
        try:
            service = self._get_service()
            result = (
                service.users()
                .history()
                .list(
                    userId="me",
                    startHistoryId=history_id,
                    historyTypes=["messageAdded"],
                )
                .execute()
            )
            for record in result.get("history", []):
                for added in record.get("messagesAdded", []):
                    msg_id = added["message"]["id"]
                    msg = await self.fetch_message(msg_id)
                    if msg:
                        messages.append(msg)
        except Exception as e:
            await AuditLog.append("list_new_messages_failed", {
                "history_id": history_id,
                "error": str(e),
            })
        return messages

    def _extract_body(self, payload: Dict[str, Any]) -> str:
        data = payload.get("body", {}).get("data", "")
        if data:
            return base64.urlsafe_b64decode(data).decode("utf-8", errors="replace")

        for part in payload.get("parts", []):
            if part.get("mimeType") == "text/plain":
                part_data = part.get("body", {}).get("data", "")
                if part_data:
                    return base64.urlsafe_b64decode(part_data).decode(
                        "utf-8", errors="replace"
                    )

        return ""

    async def send_email(
        self,
        to: str,
        subject: str,
        body: str,
        thread_id: Optional[str] = None,
    ) -> str:
        await AuditLog.append("send_email", {"to": to, "subject": subject})

        mime_msg = MIMEText(body)
        mime_msg["to"] = to
        mime_msg["subject"] = subject

        raw = base64.urlsafe_b64encode(mime_msg.as_bytes()).decode("utf-8")
        payload: Dict[str, Any] = {"raw": raw}
        if thread_id:
            payload["threadId"] = thread_id

        service = self._get_service()
        sent = service.users().messages().send(userId="me", body=payload).execute()
        gmail_id: str = sent["id"]

        await AuditLog.append("email_sent", {"gmail_id": gmail_id, "to": to})
        return gmail_id

    async def handle_webhook(self, payload: Dict[str, Any]) -> None:
        """
        Process a Gmail Pub/Sub push notification.

        Gmail sends: {"message": {"data": "<base64url JSON>", "messageId": "..."}, "subscription": "..."}
        The decoded data JSON is: {"emailAddress": "user@example.com", "historyId": "12345"}
        We use the historyId to fetch all new messages via the history API.
        """
        await AuditLog.append("webhook_received", {"keys": list(payload.keys())})

        message_data = payload.get("message", {})
        encoded = message_data.get("data", "")
        if not encoded:
            await AuditLog.append("webhook_no_data", {})
            return

        # Gmail Pub/Sub data is base64url-encoded JSON
        decoded = base64.urlsafe_b64decode(encoded + "==").decode("utf-8", errors="replace")
        notification = json.loads(decoded)
        history_id = notification.get("historyId")

        if not history_id:
            await AuditLog.append("webhook_no_history_id", {"notification": notification})
            return

        await AuditLog.append("webhook_parsed", {
            "history_id": history_id,
            "email_address": notification.get("emailAddress"),
        })

        from app.api.candidates import process_email_task
        process_email_task.delay(str(history_id))
