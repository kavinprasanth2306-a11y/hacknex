"""Base LLM interface for Gemma-powered SWE Agent."""

from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional
from pydantic import BaseModel

class ToolDefinition(BaseModel):
    name: str
    description: str
    parameters: Dict[str, Any]

class GemmaResponse(BaseModel):
    thought: str = ""
    tool_call: Optional[Dict[str, Any]] = None  # {"name": "...", "arguments": {...}}
    finish_reason: Optional[str] = None
    raw_content: str = ""

class BaseGemmaClient(ABC):
    """Abstract interface for communicating with Gemma models."""

    @abstractmethod
    def generate(self, messages: List[Dict[str, str]], tools: Optional[List[ToolDefinition]] = None) -> GemmaResponse:
        """Generate response from Gemma given message history and available tools."""
        pass

    @abstractmethod
    def get_model_identifier(self) -> str:
        """Return model name and provider descriptor."""
        pass
