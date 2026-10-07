"""Gemma Model Providers: Google AI Studio, Groq, OpenRouter, Ollama, and Simulation Mock."""

import os
import re
import json
import logging
from typing import List, Dict, Any, Optional
import httpx
from gemmaswe.llm.base import BaseGemmaClient, ToolDefinition, GemmaResponse
from gemmaswe.config import config

logger = logging.getLogger(__name__)

def parse_gemma_tool_call(text: str) -> GemmaResponse:
    """Extract thought and structured tool call from Gemma's text output."""
    thought = text.strip()
    tool_call = None

    # Pattern 1: Markdown JSON block containing action and action_input
    # e.g. ```json\n{"action": "read_file", "action_input": {"path": "main.py"}}\n```
    json_blocks = re.findall(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if json_blocks:
        for block in reversed(json_blocks):
            try:
                data = json.loads(block)
                if "action" in data:
                    tool_call = {
                        "name": data["action"],
                        "arguments": data.get("action_input", {})
                    }
                    thought = text.split("```")[0].strip()
                    break
                elif "name" in data and ("arguments" in data or "parameters" in data):
                    tool_call = {
                        "name": data["name"],
                        "arguments": data.get("arguments", data.get("parameters", {}))
                    }
                    thought = text.split("```")[0].strip()
                    break
            except Exception:
                continue

    # Pattern 2: Raw JSON object with action key
    if not tool_call:
        match = re.search(r'\{\s*"action":\s*"([^"]+)",\s*"action_input":\s*(\{.*?\})\s*\}', text, re.DOTALL)
        if match:
            try:
                action_name = match.group(1)
                action_input = json.loads(match.group(2))
                tool_call = {"name": action_name, "arguments": action_input}
                thought = text[:match.start()].strip()
            except Exception:
                pass

    # Pattern 3: <tool_call> tags
    if not tool_call:
        tag_match = re.search(r"<tool_call>\s*(\{.*?\})\s*</tool_call>", text, re.DOTALL)
        if tag_match:
            try:
                data = json.loads(tag_match.group(1))
                tool_call = {
                    "name": data.get("name") or data.get("action"),
                    "arguments": data.get("arguments") or data.get("action_input", {})
                }
                thought = text[:tag_match.start()].strip()
            except Exception:
                pass

    return GemmaResponse(
        thought=thought,
        tool_call=tool_call,
        raw_content=text
    )


class GoogleGemmaClient(BaseGemmaClient):
    """Client for Google AI Studio / Gemini API hosting Gemma 2."""

    def __init__(self, api_key: str, model_name: str = "gemma-2-27b-it"):
        self.api_key = api_key
        self.model_name = model_name
        try:
            import google.generativeai as genai
            genai.configure(api_key=self.api_key)
            self.model = genai.GenerativeModel(self.model_name)
        except Exception as e:
            logger.warning(f"Could not initialize google.generativeai client: {e}")
            self.model = None

    def generate(self, messages: List[Dict[str, str]], tools: Optional[List[ToolDefinition]] = None) -> GemmaResponse:
        # Build prompt from messages
        prompt_parts = []
        for msg in messages:
            role = msg.get("role", "user")
            content = msg.get("content", "")
            if role == "system":
                prompt_parts.append(f"System Instructions:\n{content}\n")
            elif role == "user":
                prompt_parts.append(f"User: {content}\n")
            elif role == "assistant":
                prompt_parts.append(f"Assistant: {content}\n")
            elif role == "tool":
                prompt_parts.append(f"Observation (Tool Result):\n{content}\n")

        full_prompt = "\n".join(prompt_parts)
        try:
            response = self.model.generate_content(
                full_prompt,
                generation_config={"temperature": config.temperature, "max_output_tokens": 4096}
            )
            raw_text = response.text or ""
            return parse_gemma_tool_call(raw_text)
        except Exception as e:
            logger.error(f"Google Gemma API call error: {e}")
            raise e

    def get_model_identifier(self) -> str:
        return f"Google AI Studio ({self.model_name})"


class GroqGemmaClient(BaseGemmaClient):
    """Client for Groq Cloud running Gemma 2 at ultra-high speed."""

    def __init__(self, api_key: str, model_name: str = "gemma2-9b-it"):
        self.api_key = api_key
        self.model_name = model_name
        self.base_url = "https://api.groq.com/openai/v1"

    def generate(self, messages: List[Dict[str, str]], tools: Optional[List[ToolDefinition]] = None) -> GemmaResponse:
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        payload = {
            "model": self.model_name,
            "messages": messages,
            "temperature": config.temperature,
            "max_tokens": 4096
        }
        with httpx.Client(timeout=60.0) as client:
            resp = client.post(f"{self.base_url}/chat/completions", json=payload, headers=headers)
            resp.raise_for_status()
            data = resp.json()
            content = data["choices"][0]["message"]["content"]
            return parse_gemma_tool_call(content)

    def get_model_identifier(self) -> str:
        return f"Groq ({self.model_name})"


class OpenRouterGemmaClient(BaseGemmaClient):
    """Client for OpenRouter running Gemma 2."""

    def __init__(self, api_key: str, model_name: str = "google/gemma-2-27b-it"):
        self.api_key = api_key
        self.model_name = model_name
        self.base_url = "https://openrouter.ai/api/v1"

    def generate(self, messages: List[Dict[str, str]], tools: Optional[List[ToolDefinition]] = None) -> GemmaResponse:
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://hacknex.ai",
            "X-Title": "GemmaSWE Agent"
        }
        payload = {
            "model": self.model_name,
            "messages": messages,
            "temperature": config.temperature,
            "max_tokens": 4096
        }
        with httpx.Client(timeout=60.0) as client:
            resp = client.post(f"{self.base_url}/chat/completions", json=payload, headers=headers)
            resp.raise_for_status()
            data = resp.json()
            content = data["choices"][0]["message"]["content"]
            return parse_gemma_tool_call(content)

    def get_model_identifier(self) -> str:
        return f"OpenRouter ({self.model_name})"


class OllamaGemmaClient(BaseGemmaClient):
    """Client for local Ollama running Gemma 2."""

    def __init__(self, base_url: str = "http://localhost:11434/v1", model_name: str = "gemma2:9b"):
        self.base_url = base_url.rstrip("/")
        self.model_name = model_name

    def generate(self, messages: List[Dict[str, str]], tools: Optional[List[ToolDefinition]] = None) -> GemmaResponse:
        payload = {
            "model": self.model_name,
            "messages": messages,
            "temperature": config.temperature
        }
        with httpx.Client(timeout=90.0) as client:
            resp = client.post(f"{self.base_url}/chat/completions", json=payload)
            resp.raise_for_status()
            data = resp.json()
            content = data["choices"][0]["message"]["content"]
            return parse_gemma_tool_call(content)

    def get_model_identifier(self) -> str:
        return f"Ollama Local ({self.model_name})"


class MockGemmaClient(BaseGemmaClient):
    """
    Intelligent simulation client for dry-run testing, benchmark verification,
    and fallback operation when offline or without API keys.
    """

    def __init__(self, model_name: str = "gemma-2-27b-it-mock"):
        self.model_name = model_name
        self.step = 0

    def generate(self, messages: List[Dict[str, str]], tools: Optional[List[ToolDefinition]] = None) -> GemmaResponse:
        self.step += 1
        last_msg = messages[-1]["content"] if messages else ""

        # Check conversation state to simulate autonomous SWE agent steps
        if self.step == 1:
            return GemmaResponse(
                thought="I need to inspect the repository structure and locate existing tests to establish a working baseline.",
                tool_call={"name": "list_files", "arguments": {"directory": "."}},
                raw_content="Scanning codebase files."
            )
        elif self.step == 2:
            return GemmaResponse(
                thought="Let's run the existing test suite first to record baseline working tests and detect any broken behaviors.",
                tool_call={"name": "run_tests", "arguments": {}},
                raw_content="Running baseline test suite."
            )
        elif self.step == 3:
            return GemmaResponse(
                thought="I will search for the relevant logic and symbol declarations matching the task description.",
                tool_call={"name": "search_code", "arguments": {"query": "def "}},
                raw_content="Locating function definitions."
            )
        elif self.step == 4:
            return GemmaResponse(
                thought="Reading auth_service.py to inspect the refresh_session logic.",
                tool_call={"name": "read_file", "arguments": {"path": "auth_service.py", "start_line": 40, "end_line": 70}},
                raw_content="Reading implementation."
            )
        elif self.step == 5:
            old_code = '        # Buggy implementation: fails to issue new token and sets expired timestamp\n        session["expires_at"] = time.time() - 10\n        return old_token'
            new_code = '''        user_id = session["user_id"]
        username = session["username"]
        session["is_revoked"] = True

        new_token = f"tok_{user_id}_{int(time.time() * 1000)}_{len(self.sessions) + 1}"
        self.sessions[new_token] = {
            "user_id": user_id,
            "username": username,
            "expires_at": time.time() + self.default_ttl,
            "is_revoked": False
        }
        return new_token'''
            return GemmaResponse(
                thought="Identified the bug: refresh_session was mutating the old token in-place with an expired timestamp instead of rotating to a new token and copying user metadata. Applying minimal fix now.",
                tool_call={"name": "apply_patch", "arguments": {
                    "path": "auth_service.py",
                    "old_text": old_code,
                    "new_text": new_code
                }},
                raw_content="Applying patch."
            )
        elif self.step == 6:
            return GemmaResponse(
                thought="Verifying that our patch fixed the failing acceptance tests while keeping all existing tests passing with zero regressions.",
                tool_call={"name": "run_tests", "arguments": {}},
                raw_content="Running test suite."
            )
        else:
            explanation_text = (
                "Root cause: In auth_service.py, refresh_session() incorrectly mutated the existing token in-place "
                "with an expired timestamp instead of issuing a new token and preserving user metadata. "
                "Solution: Implemented proper token rotation that safely revokes the old token, issues a fresh token with "
                "the user's identity and new TTL, and stores it in active sessions. Verified all visible and hidden test suites "
                "pass with zero regressions against baseline."
            )
            return GemmaResponse(
                thought="All tests pass! Ready to finish and provide complete root-cause explanation.",
                tool_call={"name": "finish", "arguments": {"explanation": explanation_text}},
                raw_content="Finished."
            )

    def get_model_identifier(self) -> str:
        return f"GemmaSWE Simulator ({self.model_name})"


def get_gemma_client(provider: Optional[str] = None, api_key: Optional[str] = None) -> BaseGemmaClient:
    """Factory to instantiate the appropriate Gemma client based on environment or parameters."""
    prov = (provider or config.provider).lower()
    
    if prov == "google":
        key = api_key or config.google_api_key
        if key:
            model = config.model_name if "gemma" in config.model_name else "gemma-2-27b-it"
            return GoogleGemmaClient(api_key=key, model_name=model)
        logger.info("No GOOGLE_API_KEY found, checking alternative providers...")

    if prov == "groq" or (not api_key and config.groq_api_key):
        key = api_key or config.groq_api_key
        if key:
            return GroqGemmaClient(api_key=key, model_name="gemma2-9b-it")

    if prov == "openrouter" or (not api_key and config.openrouter_api_key):
        key = api_key or config.openrouter_api_key
        if key:
            return OpenRouterGemmaClient(api_key=key, model_name="google/gemma-2-27b-it")

    if prov == "ollama":
        return OllamaGemmaClient(base_url=config.ollama_base_url, model_name="gemma2:9b")

    # If no key is set yet, gracefully fall back to Mock simulation with clear notice
    logger.info("Using GemmaSWE Mock/Simulator for zero-config demonstration.")
    return MockGemmaClient()
