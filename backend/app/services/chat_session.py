"""
Chat Session Service — session lifecycle, message exchange, AI response dispatch.

Deep module: hides MindsDB chat integration, prompt generation, session limits,
and message persistence behind a small interface.
"""
import logging
import secrets
from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.dataset import Dataset, DatasetChatSession, ChatMessage
from app.services.agent_gateway import AgentGateway
from app.services.mindsdb import MindsDBService, mindsdb_service as _default_mindsdb

logger = logging.getLogger(__name__)


class ChatSessionService:
    """Chat sessions for shared datasets.

    Construct per-request with a DB session.  MindsDBService is injected
    (not constructed internally) so callers can supply a fake in tests.
    """

    def __init__(self, db: Session, mindsdb_service: Optional[AgentGateway] = None):
        self.db = db
        self.mindsdb = mindsdb_service or _default_mindsdb

    # ── Session lifecycle ──────────────────────────────────────────────

    def create_session(
        self,
        share_token: str,
        user_id: Optional[int] = None,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Create a new chat session for a shared dataset."""
        dataset = self.db.query(Dataset).filter(
            Dataset.share_token == share_token,
            Dataset.public_share_enabled == True,
            Dataset.ai_chat_enabled == True,
            Dataset.is_deleted == False,
            Dataset.is_active == True,
        ).first()
        if not dataset:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Dataset not found or chat not enabled")

        active = self.db.query(DatasetChatSession).filter(
            DatasetChatSession.dataset_id == dataset.id,
            DatasetChatSession.is_active == True,
        ).count()
        if active >= settings.MAX_CHAT_SESSIONS_PER_DATASET:
            raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, detail="Maximum chat sessions reached for this dataset")

        session_token = secrets.token_urlsafe(32)
        system_prompt = self._build_system_prompt(dataset)

        session = DatasetChatSession(
            dataset_id=dataset.id,
            user_id=user_id,
            session_token=session_token,
            share_token=share_token,
            ip_address=ip_address,
            user_agent=user_agent,
            ai_model_name=dataset.chat_model_name or settings.DEFAULT_GEMINI_MODEL,
            system_prompt=system_prompt,
            context_data=dataset.chat_context,
        )
        self.db.add(session)
        self.db.commit()
        self.db.refresh(session)

        return {
            "session_token": session_token,
            "model_name": session.ai_model_name,
            "dataset_name": dataset.name,
            "system_prompt": system_prompt,
        }

    def send_message(self, session_token: str, message: str, message_type: str = "user") -> Dict[str, Any]:
        """Send a user message and return the AI response."""
        session = self.db.query(DatasetChatSession).filter(
            DatasetChatSession.session_token == session_token,
            DatasetChatSession.is_active == True,
        ).first()
        if not session:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Chat session not found")

        dataset = session.dataset
        if not dataset or dataset.is_deleted or not dataset.is_active or not dataset.ai_chat_enabled:
            session.is_active = False
            self.db.commit()
            raise HTTPException(status.HTTP_410_GONE, detail="Dataset is no longer available for chat")

        # Save user message
        user_msg = ChatMessage(
            session_id=session.id, message_type=message_type, content=message, created_at=datetime.utcnow(),
        )
        self.db.add(user_msg)

        try:
            start = datetime.utcnow()
            ai_response = self._get_ai_response(dataset, session, message)
            elapsed_ms = int((datetime.utcnow() - start).total_seconds() * 1000)

            ai_msg = ChatMessage(
                session_id=session.id, message_type="assistant", content=ai_response["content"],
                message_metadata=ai_response.get("metadata"),
                tokens_used=ai_response.get("tokens_used", 0),
                processing_time_ms=elapsed_ms, model_version=session.ai_model_name,
                created_at=datetime.utcnow(),
            )
            self.db.add(ai_msg)
            session.message_count += 2
            session.total_tokens_used += ai_response.get("tokens_used", 0)
            session.updated_at = datetime.utcnow()
            self.db.commit()

            return {
                "user_message": {
                    "id": user_msg.id, "content": user_msg.content,
                    "type": user_msg.message_type, "created_at": user_msg.created_at,
                },
                "ai_response": {
                    "id": ai_msg.id, "content": ai_msg.content,
                    "tokens_used": ai_msg.tokens_used,
                    "processing_time_ms": ai_msg.processing_time_ms,
                    "created_at": ai_msg.created_at,
                },
            }
        except Exception as e:
            self.db.rollback()
            err = ChatMessage(
                session_id=session.id, message_type="system",
                content=f"Error processing message: {e}", created_at=datetime.utcnow(),
            )
            self.db.add(err)
            self.db.commit()
            raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Error processing chat message")

    def get_history(self, session_token: str) -> List[Dict[str, Any]]:
        """Return all messages in a session."""
        session = self.db.query(DatasetChatSession).filter(
            DatasetChatSession.session_token == session_token,
        ).first()
        if not session:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Chat session not found")
        dataset = session.dataset
        if not dataset or dataset.is_deleted or not dataset.is_active:
            raise HTTPException(status.HTTP_410_GONE, detail="Dataset is no longer available")

        messages = self.db.query(ChatMessage).filter(
            ChatMessage.session_id == session.id,
        ).order_by(ChatMessage.created_at).all()
        return [
            {
                "id": m.id, "type": m.message_type, "content": m.content,
                "metadata": m.message_metadata, "tokens_used": m.tokens_used,
                "processing_time_ms": m.processing_time_ms, "created_at": m.created_at,
            }
            for m in messages
        ]

    def end_session(self, session_token: str) -> bool:
        """Mark a session as ended."""
        session = self.db.query(DatasetChatSession).filter(
            DatasetChatSession.session_token == session_token,
        ).first()
        if not session:
            return False
        session.is_active = False
        session.ended_at = datetime.utcnow()
        self.db.commit()
        return True

    # ── Internal ──────────────────────────────────────────────────────

    def _get_ai_response(self, dataset: Dataset, session: DatasetChatSession, user_message: str) -> Dict[str, Any]:
        """Dispatch to MindsDB for an AI response."""
        try:
            file_access = ""
            if dataset.chat_context and dataset.chat_context.get('file_url'):
                file_access = (
                    f"\nFile Access Available: YES\nFile URL: {dataset.chat_context['file_url']}\n"
                    f"File Type: {dataset.type}"
                )
            else:
                file_access = "\nFile Access Available: NO\nNote: Analysis limited to metadata and schema information."

            context = (
                f"Dataset: {dataset.name}\n"
                f"User Question: {user_message}\n\n"
                f"Dataset Context: {dataset.chat_context}\n"
                f"{file_access}\n\n"
                f"Instructions: When answering, consider whether the dataset file is accessible via URL. "
                f"If accessible, you can suggest specific analysis methods, SQL queries, or data manipulation "
                f"techniques that work with the actual file. If not accessible, focus on insights from metadata and schema."
            )

            response = self.mindsdb.ai_chat(message=context, model_name=session.ai_model_name)
            return {
                "content": response.get("answer", "I'm sorry, I couldn't process your request.") if response else "I'm sorry, I couldn't process your request.",
                "metadata": response.get("metadata") if response else None,
                "tokens_used": response.get("tokens_used", 0) if response else 0,
            }
        except Exception as e:
            return {"content": f"Error: {e}", "metadata": {"error": True}, "tokens_used": 0}

    @staticmethod
    def _build_system_prompt(dataset: Dataset) -> str:
        dtype = dataset.type.value if hasattr(dataset.type, 'value') else str(dataset.type)
        prompt = (
            f'You are an AI assistant helping users understand and analyze the dataset "{dataset.name}".\n\n'
            f"Dataset Information:\n"
            f"- Name: {dataset.name}\n"
            f"- Description: {dataset.description or 'No description provided'}\n"
            f"- Type: {dtype}\n"
            f"- Rows: {dataset.row_count or 'Unknown'}\n"
            f"- Columns: {dataset.column_count or 'Unknown'}\n\n"
        )
        if dataset.schema_info and "columns" in dataset.schema_info:
            prompt += "Dataset Schema:\n"
            for col in dataset.schema_info["columns"]:
                prompt += f"- {col.get('name', 'Unknown')}: {col.get('type', 'Unknown')}\n"
            prompt += "\n"
        if dataset.ai_summary:
            prompt += f"Dataset Summary: {dataset.ai_summary}\n\n"

        file_url = dataset.chat_context.get('file_url') if dataset.chat_context else None
        if file_url:
            prompt += (
                f"File Access:\n- Dataset is accessible via URL: {file_url}\n"
                f"- You can reference this URL for analysis or suggest how users can access the data\n"
                f"- File format: {dtype}\n\n"
            )
        else:
            prompt += "File Access:\n- Dataset file is not directly accessible via URL\n- Analysis is based on metadata and schema information only\n\n"

        prompt += (
            "You can help users:\n"
            "1. Understand the dataset structure and content\n"
            "2. Answer questions about the data\n"
            "3. Suggest analysis approaches and SQL queries when file is accessible\n"
            "4. Explain data patterns and insights\n"
            "5. Help with data interpretation\n"
            "6. Provide guidance on accessing and analyzing the data\n\n"
            "Please provide helpful, accurate, and concise responses. If you're unsure about something, let the user know."
        )
        return prompt
