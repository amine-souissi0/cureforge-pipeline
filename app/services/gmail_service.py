import base64
import json
import uuid
from email.mime.text import MIMEText
from typing import Any, Dict, List, Optional

from app.config import GOOGLE_CREDENTIALS_FILE, GOOGLE_TOKEN_FILE, GMAIL_OAUTH_REDIRECT_URI, GMAIL_PUBSUB_TOPIC
from app.schemas import AuditLog, Message

GMAIL_SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.send",
    "https://www.googleapis.com/auth/gmail.modify",
]

# Holds the flow between get_oauth_url() and complete_oauth() so the
# PKCE code_verifier generated during authorization_url() is reused
# in fetch_token(). A new Flow instance would have no verifier and fail.
_pending_oauth_flow: Optional[Any] = None


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
        global _pending_oauth_flow
        flow = GmailService.get_oauth_flow()
        auth_url, _ = flow.authorization_url(prompt="consent", access_type="offline")
        _pending_oauth_flow = flow  # preserve code_verifier for fetch_token
        return auth_url

    @staticmethod
    async def complete_oauth(code: str) -> None:
        global _pending_oauth_flow
        flow = _pending_oauth_flow if _pending_oauth_flow is not None else GmailService.get_oauth_flow()
        _pending_oauth_flow = None
        flow.fetch_token(code=code)
        GmailService._save_token(flow.credentials)
        await AuditLog.append("oauth_completed", {"service": "gmail"})

        # Auto-register Gmail watch if Pub/Sub topic is configured
        if GMAIL_PUBSUB_TOPIC:
            try:
                svc = GmailService()
                result = await svc.register_watch(GMAIL_PUBSUB_TOPIC)
                await AuditLog.append("gmail_watch_registered", {
                    "topic": GMAIL_PUBSUB_TOPIC,
                    "history_id": result.get("historyId"),
                    "expiration": result.get("expiration"),
                })
            except Exception as e:
                await AuditLog.append("gmail_watch_failed", {"error": str(e)})

    async def register_watch(self, topic_name: str) -> dict:
        """
        Register a Gmail Pub/Sub push watch on INBOX.
        Must be renewed every 7 days — call this again on token refresh.
        """
        service = self._get_service()
        result = service.users().watch(
            userId="me",
            body={"topicName": topic_name, "labelIds": ["INBOX"]},
        ).execute()
        return dict(result)

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

        # Extract plain email address and display name from "Name <email>" format
        if "<" in from_header:
            sender_name = from_header.split("<")[0].strip().strip('"')
            sender_email = from_header.split("<")[-1].rstrip(">").strip().lower()
        else:
            sender_email = from_header.strip().lower()
            sender_name = sender_email.split("@")[0]

        if not sender_name:
            sender_name = sender_email.split("@")[0]

        service = self._get_service()
        body = self._extract_body(raw.get("payload", {}))

        # Append text from PDF/Word attachments (covers empty body and resume-as-attachment cases)
        attachment_text = self._extract_attachments(service, raw["id"], raw.get("payload", {}))
        if attachment_text:
            body = (body.strip() + "\n\n" + attachment_text).strip() if body.strip() else attachment_text

        return Message(
            id=str(uuid.uuid4()),
            sender_email=sender_email,
            sender_name=sender_name,
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

    async def list_new_messages(self, history_id: str) -> tuple[List[Message], Optional[str]]:
        """
        Use the Gmail history API to find messages added since history_id.
        Returns (messages, latest_history_id) — caller should persist latest_history_id
        to avoid reprocessing on the next poll.
        """
        await AuditLog.append("list_new_messages", {"history_id": history_id})
        messages: List[Message] = []
        latest_history_id: Optional[str] = None
        try:
            service = self._get_service()
            result = (
                service.users()
                .history()
                .list(
                    userId="me",
                    startHistoryId=history_id,
                    labelId="INBOX",
                )
                .execute()
            )
            latest_history_id = str(result.get("historyId", history_id))
            seen_ids: set = set()
            for record in result.get("history", []):
                # Use messagesAdded — the only truly new messages in this history event.
                # record["messages"] covers the full thread and causes old messages to be reprocessed.
                for added in record.get("messagesAdded", []):
                    msg_ref = added.get("message", {})
                    msg_id = msg_ref.get("id")
                    if not msg_id or msg_id in seen_ids:
                        continue
                    seen_ids.add(msg_id)
                    # Only process messages that landed in INBOX
                    labels = msg_ref.get("labelIds") or []
                    if not labels:
                        meta = service.users().messages().get(
                            userId="me", id=msg_id, format="metadata",
                            metadataHeaders=["From", "Subject"],
                        ).execute()
                        labels = meta.get("labelIds", [])
                    if "INBOX" not in labels:
                        continue
                    msg = await self.fetch_message(msg_id)
                    if msg:
                        messages.append(msg)
        except Exception as e:
            await AuditLog.append("list_new_messages_failed", {
                "history_id": history_id,
                "error": str(e),
            })
        return messages, latest_history_id

    def _extract_body(self, payload: Dict[str, Any]) -> str:
        # Direct body data (simple non-multipart message)
        data = payload.get("body", {}).get("data", "")
        if data:
            return base64.urlsafe_b64decode(data).decode("utf-8", errors="replace")

        # Recurse through parts — handles multipart/alternative, multipart/mixed, etc.
        parts = payload.get("parts", [])

        # Prefer text/plain first
        for part in parts:
            if part.get("mimeType") == "text/plain":
                part_data = part.get("body", {}).get("data", "")
                if part_data:
                    return base64.urlsafe_b64decode(part_data).decode("utf-8", errors="replace")

        # Recurse into nested multipart containers
        for part in parts:
            if part.get("mimeType", "").startswith("multipart/"):
                result = self._extract_body(part)
                if result:
                    return result

        # Fall back to text/html and strip tags if no plain text found
        for part in parts:
            if part.get("mimeType") == "text/html":
                part_data = part.get("body", {}).get("data", "")
                if part_data:
                    html = base64.urlsafe_b64decode(part_data).decode("utf-8", errors="replace")
                    import re
                    return re.sub(r"<[^>]+>", " ", html).strip()

        return ""

    def _extract_attachments(self, service: Any, message_id: str, payload: Dict[str, Any]) -> str:
        """Extract text from PDF or Word attachments when email body is empty."""
        texts: list[str] = []
        self._collect_attachment_text(service, message_id, payload, texts)
        return "\n\n".join(texts)

    def _collect_attachment_text(self, service: Any, message_id: str, payload: Dict[str, Any], out: list) -> None:
        for part in payload.get("parts", []):
            mime = part.get("mimeType", "")
            filename = part.get("filename", "")
            attachment_id = part.get("body", {}).get("attachmentId")

            if attachment_id and filename:
                try:
                    att = service.users().messages().attachments().get(
                        userId="me", messageId=message_id, id=attachment_id
                    ).execute()
                    data = base64.urlsafe_b64decode(att["data"])

                    if mime == "application/pdf" or filename.lower().endswith(".pdf"):
                        text = self._pdf_to_text(data)
                        if text:
                            out.append(f"[Attachment: {filename}]\n{text}")

                    elif mime in ("application/vnd.openxmlformats-officedocument.wordprocessingml.document",) or filename.lower().endswith(".docx"):
                        text = self._docx_to_text(data)
                        if text:
                            out.append(f"[Attachment: {filename}]\n{text}")

                except Exception:
                    pass

            # Recurse into nested multipart
            if mime.startswith("multipart/"):
                self._collect_attachment_text(service, message_id, part, out)

    @staticmethod
    def _pdf_to_text(data: bytes) -> str:
        try:
            import io
            from pypdf import PdfReader
            reader = PdfReader(io.BytesIO(data))
            return "\n".join(page.extract_text() or "" for page in reader.pages).strip()
        except Exception:
            return ""

    @staticmethod
    def _docx_to_text(data: bytes) -> str:
        try:
            import io
            import zipfile
            import xml.etree.ElementTree as ET
            with zipfile.ZipFile(io.BytesIO(data)) as z:
                with z.open("word/document.xml") as f:
                    tree = ET.parse(f)
            ns = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
            texts = [node.text for node in tree.iter(f"{ns}t") if node.text]
            return " ".join(texts).strip()
        except Exception:
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

        # Gmail Pub/Sub data is base64url-encoded JSON — pad to multiple of 4
        padding = 4 - len(encoded) % 4
        padded = encoded + "=" * (padding % 4)
        decoded = base64.urlsafe_b64decode(padded).decode("utf-8", errors="replace")
        if not decoded.strip():
            await AuditLog.append("webhook_empty_data", {})
            return
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
