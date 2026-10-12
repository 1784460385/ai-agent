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


class IndexResponse(BaseModel):
    status: str
    chunks_indexed: Optional[int] = None
    message: Optional[str] = None


class UploadResponse(BaseModel):
    status: str
    filename: str


class DocumentInfo(BaseModel):
    name: str
    size: int


class DocumentListResponse(BaseModel):
    files: list[DocumentInfo]


class StatsResponse(BaseModel):
    chunks: int
