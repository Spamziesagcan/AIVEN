from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=4000)


class MessageInput(BaseModel):
    role: str
    content: str


class Message(BaseModel):
    id: str
    role: str
    content: str
    timestamp: str


class ConversationSummary(BaseModel):
    id: str
    title: str
    created_at: str
    updated_at: str


class ConversationDetail(ConversationSummary):
    messages: List[Message] = Field(default_factory=list)


class MetadataTimestamps(BaseModel):
    started_at: str
    finished_at: str


class ChatMeta(BaseModel):
    provider: Optional[str] = None
    model: Optional[str] = None
    latency_ms: Optional[int] = None
    usage: Optional[Dict[str, Any]] = None
    timestamps: MetadataTimestamps
    status: str
    error: Optional[str] = None
    conversation_id: Optional[str] = None
    request_id: Optional[str] = None
    input_preview: str = ""
    output_preview: str = ""


class IngestionEvent(BaseModel):
    event_id: Optional[str] = None
    event: str = Field(default="chat_request")
    conversation_id: Optional[str] = None
    prompt: Optional[str] = None
    context: List[MessageInput] = Field(default_factory=list)
    published_at: Optional[str] = None
    meta: ChatMeta


class ChatResponse(BaseModel):
    reply: Message
    conversation_id: str
    meta: ChatMeta
