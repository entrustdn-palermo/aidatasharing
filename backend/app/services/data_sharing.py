"""
DataSharingService — backward-compatible delegating wrapper.

This module is kept for call-site compatibility.  New code should import
from the three focused services directly:

    from app.services.access_control import AccessControlService
    from app.services.sharing import SharingService
    from app.services.chat_session import ChatSessionService
"""
from typing import List, Optional, Dict, Any
from sqlalchemy.orm import Session
from app.models.user import User
from app.models.dataset import Dataset, DatasetAccessLog, DatasetType
from app.models.organization import DataSharingLevel
from datetime import datetime
import logging

from fastapi import HTTPException, status

from app.services.access_control import AccessControlService
from app.services.sharing import SharingService
from app.services.chat_session import ChatSessionService
from app.services.agent_gateway import AgentGateway
from app.services.mindsdb import MindsDBService, mindsdb_service as _default_mindsdb

logger = logging.getLogger(__name__)


class DataSharingService:
    """Backward-compatible wrapper that delegates to the three focused services."""

    def __init__(self, db: Session, mindsdb_service: Optional[AgentGateway] = None):
        self.db = db
        self.access = AccessControlService(db)
        self.sharing = SharingService(db)
        self.chat_session = ChatSessionService(db, mindsdb_service=mindsdb_service)
        # Retained for backward compat — new code injects MindsDBService explicitly
        self.mindsdb_service: AgentGateway = mindsdb_service or _default_mindsdb
    
    # ── Access control delegation ─────────────────────────────────────

    def can_access_dataset(self, user: User, dataset: Dataset) -> bool:
        return self.access.can_access_dataset(user, dataset)

    def can_download_dataset(self, user: User, dataset: Dataset) -> bool:
        return self.access.can_download_dataset(user, dataset)

    def check_download_rate_limit(self, user: User) -> Dict[str, Any]:
        return self.access.check_download_rate_limit(user)

    def log_download_attempt(
        self, user: User, dataset: Dataset, success: bool,
        error_message: Optional[str] = None, ip_address: Optional[str] = None,
    ) -> bool:
        return self.access.log_download_attempt(user, dataset, success, error_message, ip_address)

    def get_accessible_datasets(self, user: User,
                                sharing_level: Optional[DataSharingLevel] = None,
                                include_inactive: bool = False,
                                include_deleted: bool = False,
                                dataset_type: Optional[DatasetType] = None,
                                skip: Optional[int] = None,
                                limit: Optional[int] = None) -> List[Dataset]:
        return self.access.get_accessible_datasets(
            user, sharing_level, include_inactive, include_deleted,
            dataset_type, skip, limit,
        )

    def get_organization_datasets(self, org_id: int, user: User) -> List[Dataset]:
        return self.access.get_organization_datasets(org_id, user)

    def log_access(self, user: User, dataset: Dataset, access_type: str,
                   ip_address: Optional[str] = None,
                   user_agent: Optional[str] = None,
                   details: Optional[Dict[str, Any]] = None) -> bool:
        return self.access.log_access(user, dataset, access_type, ip_address, user_agent, details)

    def get_organization_stats(self, org_id: int, user: User) -> dict:
        return self.access.get_organization_stats(org_id, user)

    def validate_dataset_creation(self, user: User, org_id: int) -> bool:
        return self.access.validate_dataset_creation(user, org_id)

    # ── Sharing delegation ────────────────────────────────────────────

    def create_share_link(self, dataset_id: int, user_id: int,
                          password: Optional[str] = None,
                          enable_chat: bool = True) -> Dict[str, Any]:
        return self.sharing.create_share_link(dataset_id, user_id, password, enable_chat)

    async def get_shared_dataset(self, share_token: str,
                                  password: Optional[str] = None,
                                  ip_address: Optional[str] = None,
                                  user_agent: Optional[str] = None) -> Dict[str, Any]:
        return await self.sharing.get_shared_dataset(share_token, password, ip_address, user_agent)

    def verify_share_password(self, dataset: Dataset, password: Optional[str]) -> bool:
        return self.sharing.verify_password(dataset, password)

    def update_sharing_level(self, user: User, dataset: Dataset,
                             new_level: DataSharingLevel) -> bool:
        return self.sharing.update_sharing_level(user, dataset, new_level)

    def get_sharing_stats(self, org_id: int, user: User) -> dict:
        return self.sharing.get_sharing_stats(org_id, user)

    def get_organization_shared_datasets(self, org_id: int, user: User) -> List[Dataset]:
        return self.sharing.get_org_shared_datasets(org_id, user)

    def get_dataset_analytics(self, dataset_id: int, user_id: int) -> Dict[str, Any]:
        return self.sharing.get_dataset_analytics(dataset_id, user_id)

    # ── Chat session delegation ───────────────────────────────────────

    def create_chat_session(self, share_token: str, user_id: Optional[int] = None,
                            ip_address: Optional[str] = None,
                            user_agent: Optional[str] = None) -> Dict[str, Any]:
        return self.chat_session.create_session(share_token, user_id, ip_address, user_agent)

    def send_chat_message(self, session_token: str, message: str,
                          message_type: str = "user") -> Dict[str, Any]:
        return self.chat_session.send_message(session_token, message, message_type)

    def get_chat_history(self, session_token: str) -> List[Dict[str, Any]]:
        return self.chat_session.get_history(session_token)

    def end_chat_session(self, session_token: str) -> bool:
        return self.chat_session.end_session(session_token)

    # ── Shared-dataset chat & analysis ──────────────────────────────────

    async def chat_with_shared_dataset(
        self,
        share_token: str,
        chat_request,
        request=None,
    ) -> Dict[str, Any]:
        """Chat with a shared dataset (public endpoint)."""
        from app.services.agent_gateway import AgentGateway
        from app.services.mindsdb import MindsDBService
        from app.core.config import settings
        from app.models.dataset import Dataset, DatasetChatSession, ChatMessage
        from app.services.prompt_templates import with_anton_context

        dataset = self.db.query(Dataset).filter(
            Dataset.share_token == share_token,
            Dataset.public_share_enabled == True,
            Dataset.ai_chat_enabled == True,
            Dataset.is_deleted == False
        ).first()

        if not dataset:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Shared dataset not found or chat not enabled")

        self.sharing.require_password(dataset, chat_request.password)

        if not dataset.allow_ai_chat:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Chat is disabled for this dataset")

        if len(chat_request.message or "") > 4000:
            raise HTTPException(status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail="Message is too long")

        if not chat_request.session_token:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="A valid share access session is required for chat")

        session = self.db.query(DatasetChatSession).filter(
            DatasetChatSession.session_token == chat_request.session_token,
            DatasetChatSession.dataset_id == dataset.id,
            DatasetChatSession.share_token == share_token,
            DatasetChatSession.is_active == True
        ).first()

        if not session:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Share chat session has expired")

        if session.message_count >= settings.MAX_CHAT_SESSIONS_PER_DATASET:
            raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail="Shared chat message limit reached for this session")

        mindsdb_service_inst: AgentGateway = MindsDBService()

        anton_message = with_anton_context(chat_request.message, dataset, session)

        if getattr(settings, 'USE_AGENT_BASED_CHAT', True):
            chat_response = await mindsdb_service_inst.chat_with_dataset_agent(
                dataset_id=dataset.id, message=anton_message, db=self.db,
                session_id=chat_request.session_token, stream=True
            )
        else:
            chat_response = await mindsdb_service_inst.chat_with_dataset(
                dataset_id=str(dataset.id), message=anton_message,
                user_id=None, session_id=chat_request.session_token,
                organization_id=dataset.organization_id
            )

        chat_response = await self._attach_shared_chat_visualizations(
            chat_response=chat_response, dataset=dataset, message=chat_request.message,
            mindsdb_service=mindsdb_service_inst, max_visualizations=3
        )

        answer_text = chat_response.get("answer") or chat_response.get("response") or ""
        self.db.add(ChatMessage(
            session_id=session.id, message_type="user",
            content=chat_request.message,
            message_metadata={"source": "public_share", "anton_context": True}
        ))
        self.db.add(ChatMessage(
            session_id=session.id, message_type="assistant",
            content=str(answer_text),
            message_metadata={
                "source": chat_response.get("source"),
                "agent_name": chat_response.get("agent_name"),
                "has_visualizations": chat_response.get("has_visualizations", False),
                "visualization_count": chat_response.get("visualization_count", 0)
            },
            ai_model_version=chat_response.get("model")
        ))

        session.message_count += 1
        session.updated_at = datetime.utcnow()
        self.db.commit()

        return chat_response

    async def _attach_shared_chat_visualizations(
        self,
        chat_response: Dict[str, Any],
        dataset,
        message: Optional[str],
        mindsdb_service,
        max_visualizations: int = 3,
    ) -> Dict[str, Any]:
        """Attach visualization data to a chat response if the message requests it."""
        from app.services.data_visualization import get_visualization_service, sanitize_visualization_payload

        if not self._is_visualization_prompt(message):
            chat_response.setdefault("visualizations", [])
            chat_response.setdefault("data_analysis", {})
            chat_response.setdefault("has_visualizations", False)
            chat_response.setdefault("visualization_count", 0)
            return chat_response

        try:
            dataset_df = await mindsdb_service.load_dataset_for_visualization(dataset, self.db)
            if dataset_df is None or dataset_df.empty:
                chat_response.setdefault("visualizations", [])
                chat_response.setdefault("data_analysis", {})
                chat_response["has_visualizations"] = False
                chat_response["visualization_count"] = 0
                chat_response["visualization_message"] = "Anton could answer the question, but this shared data source is not tabular enough to chart automatically."
                return chat_response

            viz_service = get_visualization_service(getattr(mindsdb_service, "api_key", None))
            data_analysis = viz_service.analyze_dataset(dataset_df, dataset.name)
            visualizations = viz_service.generate_chat_visualizations(
                dataset_df, query=message or "", max_visualizations=max_visualizations
            )

            chat_response["visualizations"] = sanitize_visualization_payload(visualizations)
            chat_response["data_analysis"] = sanitize_visualization_payload(data_analysis)
            chat_response["has_visualizations"] = len(visualizations) > 0
            chat_response["visualization_count"] = len(visualizations)
            chat_response["source"] = "anton_shared_chat"
        except Exception as e:
            logger.warning(f"Shared chat visualization generation failed for dataset {getattr(dataset, 'id', 'unknown')}: {e}")
            chat_response.setdefault("visualizations", [])
            chat_response.setdefault("data_analysis", {})
            chat_response["has_visualizations"] = False
            chat_response["visualization_count"] = 0
            chat_response["visualization_message"] = "Anton answered the question, but chart generation failed for this request."

        return chat_response

    @staticmethod
    def _is_visualization_prompt(message: Optional[str]) -> bool:
        if not message:
            return False
        message_lower = message.lower()
        return any(keyword in message_lower for keyword in [
            'visualiz', 'chart', 'graph', 'plot', 'diagram', 'show', 'display',
            'trend', 'distribution', 'correlation', 'relationship', 'compare',
            'histogram', 'scatter', 'heatmap', 'bar', 'line', 'pie', 'dashboard'
        ])

    async def analyze_shared_dataset_with_anton(
        self,
        share_token: str,
        analyze_request,
        request=None,
    ) -> Dict[str, Any]:
        """Analyze a shared dataset using the Anton data analyst experience."""
        from app.services.agent_gateway import AgentGateway
        from app.services.mindsdb import MindsDBService
        from app.services.data_visualization import get_visualization_service, sanitize_visualization_payload
        from app.core.app_config import get_app_config
        from app.models.dataset import Dataset

        dataset = self.db.query(Dataset).filter(
            Dataset.share_token == share_token,
            Dataset.public_share_enabled == True,
            Dataset.ai_chat_enabled == True,
            Dataset.is_deleted == False
        ).first()

        if not dataset:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Shared dataset not found or analysis not enabled")

        self.sharing.require_password(dataset, analyze_request.password)

        if not dataset.allow_ai_chat:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Analysis is disabled for this dataset")

        if analyze_request.query and len(analyze_request.query) > 4000:
            raise HTTPException(status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail="Analysis query is too long")

        mindsdb_service_inst: AgentGateway = MindsDBService()
        prompt = analyze_request.query or (
            "You are Anton, a shared-data analyst powered by MindsDB. Analyze this shared dataset for the recipient. "
            "Summarize the dataset structure, key patterns, data quality issues, notable distributions, "
            "potential correlations, recommended charts, and useful follow-up questions. Only analyze this shared dataset."
        )

        answer = "Anton analyzed the shared dataset and generated the summary below."
        agent_name = "Anton"
        model = None
        try:
            chat_response = await mindsdb_service_inst.chat_with_dataset_agent(
                dataset_id=dataset.id, message=prompt, db=self.db,
                session_id=None, stream=True
            )
            answer = chat_response.get("answer") or chat_response.get("response") or answer
            agent_name = chat_response.get("agent_name") or agent_name
            model = chat_response.get("model")
        except Exception as e:
            logger.warning(f"Anton narrative analysis failed for shared dataset {dataset.id}: {e}")

        data_analysis: Dict[str, Any] = {}
        visualizations: list[Dict[str, Any]] = []
        max_visualizations = min(max(analyze_request.max_visualizations, 1), 5)

        try:
            dataset_df = await mindsdb_service_inst.load_dataset_for_visualization(dataset, self.db)
            if dataset_df is not None and not dataset_df.empty:
                app_config = get_app_config()
                viz_service = get_visualization_service(app_config.integrations.GOOGLE_API_KEY)
                data_analysis = viz_service.analyze_dataset(dataset_df, dataset.name)
                visualizations = viz_service.generate_chat_visualizations(
                    dataset_df,
                    query=analyze_request.query or "Generate useful visualizations for this shared dataset",
                    max_visualizations=max_visualizations
                )
                data_analysis = sanitize_visualization_payload(data_analysis)
                visualizations = sanitize_visualization_payload(visualizations)
        except Exception as e:
            logger.warning(f"Anton visualization generation failed for shared dataset {dataset.id}: {e}")

        dataset.share_view_count += 1
        dataset.last_accessed = datetime.utcnow()
        self.db.commit()

        return {
            "success": True,
            "dataset_id": dataset.id,
            "dataset_name": dataset.name,
            "answer": answer,
            "data_analysis": data_analysis,
            "visualizations": visualizations,
            "has_visualizations": len(visualizations) > 0,
            "visualization_count": len(visualizations),
            "source": "anton_shared_analysis",
            "agent_name": agent_name,
            "model": model,
            "timestamp": datetime.utcnow().isoformat()
        }

    async def download_shared_dataset(
        self,
        share_token: str,
        password: Optional[str] = None,
        session_token: Optional[str] = None,
        request=None,
    ):
        """Download a shared dataset (public endpoint)."""
        from fastapi.responses import FileResponse
        from app.models.dataset import Dataset, DatasetFile
        from app.services.storage import storage_service

        dataset = self.db.query(Dataset).filter(
            Dataset.share_token == share_token,
            Dataset.public_share_enabled == True,
            Dataset.allow_download == True,
            Dataset.is_deleted == False
        ).first()

        if not dataset:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Shared dataset not found or download not allowed")

        self.sharing.require_password(dataset, password)

        if session_token:
            from app.models.dataset import ShareAccessSession
            session = self.db.query(ShareAccessSession).filter(
                ShareAccessSession.session_token == session_token,
                ShareAccessSession.dataset_id == dataset.id,
                ShareAccessSession.is_active == True
            ).first()
            if session:
                session.files_downloaded += 1
                session.last_activity_at = datetime.utcnow()
                self.db.commit()

        if dataset.source_url and dataset.source_url.startswith(('http://', 'https://')):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Cannot download external URL datasets. This dataset is hosted externally.")

        # Multi-file download
        if dataset.is_multi_file_dataset or not dataset.source_url:
            dataset_files = self.db.query(DatasetFile).filter(
                DatasetFile.dataset_id == dataset.id,
                DatasetFile.is_deleted == False
            ).all()

            if dataset_files:
                if dataset.is_multi_file_dataset and len(dataset_files) > 1:
                    import tempfile, zipfile

                    temp_zip = tempfile.NamedTemporaryFile(delete=False, suffix='.zip')
                    try:
                        with zipfile.ZipFile(temp_zip, 'w', zipfile.ZIP_DEFLATED) as zip_file:
                            for dataset_file in dataset_files:
                                try:
                                    file_path_to_retrieve = dataset_file.relative_path or dataset_file.file_path
                                    file_content = await storage_service.retrieve_dataset_file(file_path_to_retrieve)
                                    if file_content:
                                        zip_file.writestr(dataset_file.filename, file_content)
                                    else:
                                        logger.warning(f"File not found: {dataset_file.filename}")
                                except Exception as e:
                                    logger.error(f"Failed to add file {dataset_file.filename} to zip: {str(e)}")
                        temp_zip.close()

                        download_name = f"{dataset.name}_all_files.zip"
                        return FileResponse(
                            path=temp_zip.name, filename=download_name,
                            media_type='application/zip',
                            headers={
                                "Content-Disposition": f'attachment; filename="{download_name}"',
                                "Cache-Control": "no-cache, no-store, must-revalidate",
                                "Pragma": "no-cache", "Expires": "0"
                            }
                        )
                    except Exception as e:
                        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to create zip: {str(e)}")
                else:
                    # Single file download
                    dataset_file = dataset_files[0]
                    file_path_to_retrieve = dataset_file.relative_path or dataset_file.file_path
                    file_content = await storage_service.retrieve_dataset_file(file_path_to_retrieve)
                    if file_content:
                        import tempfile
                        temp_file = tempfile.NamedTemporaryFile(delete=False)
                        if isinstance(file_content, bytes):
                            temp_file.write(file_content)
                        else:
                            temp_file.write(file_content.encode('utf-8') if isinstance(file_content, str) else file_content)
                        temp_file.close()
                        return FileResponse(
                            path=temp_file.name, filename=dataset_file.filename,
                            media_type='application/octet-stream',
                            headers={
                                "Content-Disposition": f'attachment; filename="{dataset_file.filename}"',
                                "Cache-Control": "no-cache"
                            }
                        )

        # Legacy file download
        if dataset.file_path:
            file_content = await storage_service.retrieve_dataset_file(dataset.file_path)
            if file_content:
                from app.utils.file_utils import sanitize_filename
                import tempfile
                temp_file = tempfile.NamedTemporaryFile(delete=False)
                if isinstance(file_content, bytes):
                    temp_file.write(file_content)
                else:
                    temp_file.write(file_content.encode('utf-8') if isinstance(file_content, str) else file_content)
                temp_file.close()
                safe_name = sanitize_filename(dataset.name, "download")
                return FileResponse(
                    path=temp_file.name, filename=safe_name,
                    media_type='application/octet-stream',
                    headers={"Content-Disposition": f'attachment; filename="{safe_name}"', "Cache-Control": "no-cache"}
                )

        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No downloadable files found for this dataset") 