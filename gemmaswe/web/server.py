"""FastAPI server with WebSockets for real-time GemmaSWE web dashboard."""

import sys
import os
import json
import asyncio
from pathlib import Path
from typing import Dict, Any, Optional

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, HTMLResponse
from pydantic import BaseModel
import uvicorn

from gemmaswe.config import config
from gemmaswe.llm.gemma_provider import get_gemma_client
from gemmaswe.agent.swe_agent import GemmaSweAgent
from gemmaswe.benchmark.suite import BenchmarkEvaluator
from gemmaswe.benchmark.scenarios.auth_scenario import setup_auth_repo
from gemmaswe.benchmark.scenarios.ratelimit_scenario import setup_ratelimit_repo

app = FastAPI(title="GemmaSWE Dashboard", version="1.0.0")

STATIC_DIR = Path(__file__).parent / "static"
STATIC_DIR.mkdir(parents=True, exist_ok=True)
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

class RunRequest(BaseModel):
    repo_path: Optional[str] = None
    scenario: Optional[str] = "auth_session_bugfix"
    task: Optional[str] = None
    provider: Optional[str] = None
    api_key: Optional[str] = None

@app.get("/")
async def serve_index():
    index_file = STATIC_DIR / "index.html"
    if index_file.exists():
        return FileResponse(str(index_file))
    return HTMLResponse("<h1>GemmaSWE Dashboard</h1><p>UI loading...</p>")

@app.get("/api/config")
async def get_system_config():
    return {
        "provider": config.provider,
        "model": config.model_name,
        "max_iterations": config.max_iterations,
        "google_key_configured": bool(config.google_api_key),
        "groq_key_configured": bool(config.groq_api_key)
    }

@app.get("/api/scenarios")
async def list_scenarios():
    return [
        {
            "id": "auth_session_bugfix",
            "name": "Scenario 1: Microservice Token Expiry & Session Refresh Bug",
            "type": "Single-file targeted bugfix with regression guard",
            "description": "Fix invalid session revocation in auth_service.py while ensuring all baseline authentication tests still pass.",
            "tests": ["test_auth_baseline.py (visible)", "test_token_refresh.py (acceptance)", "hidden_tests.py (30 pts)"]
        },
        {
            "id": "ratelimit_preservation",
            "name": "Scenario 2: Rate Limiter Middleware & Workflow Preservation",
            "type": "Multi-file feature addition without breaking contracts",
            "description": "Add IP sliding window rate limiting while keeping ordering and catalog workflows 100% operational.",
            "tests": ["test_existing_workflow.py (visible)", "hidden_tests.py (30 pts)"]
        }
    ]

@app.get("/api/scenario-files")
async def get_scenario_files(scenario: str = "auth_session_bugfix"):
    """Return files for the selected scenario."""
    import tempfile
    temp_dir = Path(tempfile.mkdtemp(prefix="preview_"))
    try:
        if scenario == "ratelimit_preservation":
            setup_ratelimit_repo(temp_dir)
        else:
            setup_auth_repo(temp_dir)
        
        files = []
        for p in temp_dir.glob("*.py"):
            files.append({
                "name": p.name,
                "path": p.name,
                "size": p.stat().st_size,
                "is_test": "test" in p.name.lower() or "hidden" in p.name.lower()
            })
        return {"scenario": scenario, "files": sorted(files, key=lambda x: x["name"])}
    finally:
        import shutil
        shutil.rmtree(temp_dir, ignore_errors=True)

@app.get("/api/file-content")
async def get_file_content(scenario: str = "auth_session_bugfix", path: str = "auth_service.py"):
    """Fetch content of a file in the scenario."""
    import tempfile, shutil
    temp_dir = Path(tempfile.mkdtemp(prefix="preview_"))
    try:
        if scenario == "ratelimit_preservation":
            setup_ratelimit_repo(temp_dir)
        else:
            setup_auth_repo(temp_dir)
        
        target = temp_dir / path
        if target.exists() and target.is_file():
            return {"path": path, "content": target.read_text(encoding="utf-8")}
        return {"error": "File not found"}
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


@app.websocket("/ws/agent")
async def websocket_agent_run(websocket: WebSocket):
    await websocket.accept()
    loop = asyncio.get_event_loop()

    try:
        data_text = await websocket.receive_text()
        params = json.loads(data_text)
        
        scenario_id = params.get("scenario", "auth_session_bugfix")
        provider = params.get("provider", config.provider)
        api_key = params.get("api_key", "")
        custom_task = params.get("task")
        custom_repo = params.get("repo_path")

        def emit_event(event: Dict[str, Any]):
            asyncio.run_coroutine_threadsafe(
                websocket.send_text(json.dumps(event)),
                loop
            )

        # Prepare workspace for scenario
        import tempfile
        temp_dir = Path(tempfile.mkdtemp(prefix="gemmaswe_web_"))

        if custom_repo and Path(custom_repo).exists():
            target_repo = Path(custom_repo)
            task_desc = custom_task or "Inspect repository, find bugs, and verify all tests pass."
        elif scenario_id == "ratelimit_preservation":
            setup_ratelimit_repo(temp_dir)
            target_repo = temp_dir
            task_desc = (
                "Verify and complete the sliding-window RateLimiter in middleware.py and ensure ApiApp integrates it "
                "properly in app.py without breaking any existing catalog or order placement endpoints."
            )
        else:
            setup_auth_repo(temp_dir)
            target_repo = temp_dir
            task_desc = (
                "Fix the session refresh bug in auth_service.py so that refresh_session returns a valid active token "
                "with user info, revokes the old token, and passes all tests in test_auth_baseline.py and test_token_refresh.py."
            )

        client = get_gemma_client(provider=provider, api_key=api_key)
        agent = GemmaSweAgent(repo_path=str(target_repo), client=client, event_callback=emit_event)

        # Run agent in threadpool so it doesn't block async event loop
        result = await asyncio.to_thread(
            agent.run,
            task_description=task_desc,
            test_command=f"{sys.executable} -m unittest discover -v"
        )

        # Run hidden tests for 30 points
        import subprocess
        hidden_proc = subprocess.run(
            [sys.executable, "-m", "unittest", "hidden_tests.py"],
            cwd=str(target_repo),
            capture_output=True,
            text=True
        )
        hidden_passed = (hidden_proc.returncode == 0)
        
        result["hidden_tests"] = {
            "passed": hidden_passed,
            "score": 30 if hidden_passed else 0,
            "output": hidden_proc.stdout or hidden_proc.stderr
        }

        await websocket.send_text(json.dumps({
            "type": "final_benchmark",
            "result": result
        }))

    except WebSocketDisconnect:
        pass
    except Exception as e:
        await websocket.send_text(json.dumps({"type": "error", "error": str(e)}))
    finally:
        pass

def start_server(host: str = "127.0.0.1", port: int = 8000):
    uvicorn.run(app, host=host, port=port)
