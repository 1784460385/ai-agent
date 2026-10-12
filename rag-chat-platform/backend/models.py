from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class ModelConfig(BaseModel):
    model_config = ConfigDict(protected_namespaces=())

    api_key: str = Field(..., min_length=1, description="用户提供的 DeepSeek API Key")
    base_url: str = Field(default="https://api.deepseek.com")
    model_name: str = Field(default="deepseek-flash")


class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=4000)
    config: ModelConfig
    conversation_id: Optional[int] = None


class IndexResponse(BaseModel):
    status: str
    chunks_indexed: Optional[int] = None
    message: Optional[str] = None
    departments: Optional[dict[str, int]] = None


class UploadResponse(BaseModel):
    status: str
    filename: str
    department: str


class DocumentInfo(BaseModel):
    name: str
    size: int
    department: Optional[str] = None
    parse_status: Optional[str] = None
    parse_error: Optional[str] = None


class DocumentListResponse(BaseModel):
    files: list[DocumentInfo]


class DepartmentInfo(BaseModel):
    key: str
    name: str
    description: str
    chunk_count: int
    files: list[DocumentInfo]


class DepartmentListResponse(BaseModel):
    departments: list[DepartmentInfo]


class FolderCreateRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=40)


class StatsResponse(BaseModel):
    chunks: int


class ConversationSummary(BaseModel):
    id: int
    title: str
    model_name: str
    created_at: str


class ConversationMessage(BaseModel):
    role: str
    content: str
    sources: Optional[list[dict]] = None
    router: Optional[dict] = None


class ConversationDetail(ConversationSummary):
    messages: list[ConversationMessage]


class ConversationListResponse(BaseModel):
    conversations: list[ConversationSummary]
