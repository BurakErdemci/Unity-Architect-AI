from typing import List, Optional
from pydantic import BaseModel


class AuthRequest(BaseModel):
    username: str
    password: str


class AnalysisRequest(BaseModel):
    code: str
    language: str = "tr"
    user_id: int


class AIConfigRequest(BaseModel):
    user_id: int
    provider_type: str
    model_name: str
    api_key: str


class UpdateFileRequest(BaseModel):
    file_path: str
    new_code: str


class RenameRequest(BaseModel):
    title: str


class APIKeySaveRequest(BaseModel):
    provider_type: str
    api_key: str


class NewConversationRequest(BaseModel):
    user_id: int
    title: str = "Yeni Sohbet"


class ChatRequest(BaseModel):
    conversation_id: int
    message: str
    language: str = "tr"
    user_id: int
    mode: str = "analysis"
    editor_code: str = ""
    use_thinking: bool = False
    thinking_level: str = "medium" # off | low | medium | high
    generation_confirmed: bool = False
    generation_mode: str = "auto"  # auto | plan | step
    images: Optional[List[str]] = None
    # Video ekleri: [{"kind":"path","path":...} | {"kind":"url","url":...}]. Backend
    # bunları kare data-URI'leri + transkripte çevirip images'a katar (video_extract).
    videos: Optional[List[dict]] = None
    # Claude-only (subscription + model_name "claude-" ile başlar). Diğer sağlayıcılarda
    # yok sayılır. effort_level → ClaudeAgentOptions.effort; ultracode → mesaj keyword'ü.
    effort_level: str = "medium"  # low | medium | high | max
    ultracode: bool = False


class WorkspaceRequest(BaseModel):
    user_id: int
    path: str


class WriteFileRequest(BaseModel):
    file_path: str
    content: str
    workspace_path: str
