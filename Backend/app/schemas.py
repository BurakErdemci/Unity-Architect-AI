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
    use_multi_agent: bool = True
    force_claude_coder: bool = False


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
    use_kb: bool = True


class WorkspaceRequest(BaseModel):
    user_id: int
    path: str


class WriteFileRequest(BaseModel):
    file_path: str
    content: str
    workspace_path: str
