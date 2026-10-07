"""Configuration management for GemmaSWE Agent."""

import os
from pathlib import Path
from pydantic import BaseModel, Field
from dotenv import load_dotenv

# Load .env if present
load_dotenv()

class SweConfig(BaseModel):
    provider: str = Field(default_factory=lambda: os.getenv("GEMMA_PROVIDER", "google").lower())
    model_name: str = Field(default_factory=lambda: os.getenv("GEMMA_MODEL", "gemma-2-27b-it"))
    
    # API Keys
    google_api_key: str = Field(default_factory=lambda: os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY") or "")
    groq_api_key: str = Field(default_factory=lambda: os.getenv("GROQ_API_KEY", ""))
    openrouter_api_key: str = Field(default_factory=lambda: os.getenv("OPENROUTER_API_KEY", ""))
    ollama_base_url: str = Field(default_factory=lambda: os.getenv("OLLAMA_BASE_URL", "http://localhost:11434/v1"))
    
    # Execution thresholds
    max_iterations: int = Field(default_factory=lambda: int(os.getenv("MAX_ITERATIONS", "15")))
    max_test_retries: int = Field(default_factory=lambda: int(os.getenv("MAX_TEST_RETRIES", "4")))
    auto_rollback_on_regression: bool = Field(default_factory=lambda: os.getenv("AUTO_ROLLBACK_ON_REGRESSION", "true").lower() == "true")
    timeout_seconds: int = Field(default=60)
    temperature: float = Field(default=0.1)  # Low temp for accurate code generation

config = SweConfig()
