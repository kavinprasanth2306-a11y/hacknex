"""Benchmark scenario 2: Multi-file Feature Addition - Rate Limiter with Workflow Preservation."""

from pathlib import Path

def setup_ratelimit_repo(target_dir: Path):
    """Generates a multi-file API codebase requiring rate limiting while keeping existing routes intact."""
    target_dir.mkdir(parents=True, exist_ok=True)

    # config.py
    (target_dir / "config.py").write_text('''
MAX_REQUESTS_PER_MINUTE = 5
RATE_LIMIT_ENABLED = True
''', encoding="utf-8")

    # router.py
    (target_dir / "router.py").write_text('''from typing import Dict, Any

class OrderRouter:
    """Handles existing core ordering and catalog workflows."""

    def __init__(self):
        self.orders = {}
        self.catalog = {"item_1": 100, "item_2": 250}

    def get_catalog(self) -> Dict[str, Any]:
        return {"items": self.catalog}

    def place_order(self, user_id: str, item_id: str, quantity: int) -> Dict[str, Any]:
        if item_id not in self.catalog:
            return {"status": "error", "message": "Unknown item"}
        total = self.catalog[item_id] * quantity
        order_id = f"ord_{len(self.orders) + 1}"
        self.orders[order_id] = {"user_id": user_id, "item_id": item_id, "total": total}
        return {"status": "success", "order_id": order_id, "total": total}
''', encoding="utf-8")

    # middleware.py
    (target_dir / "middleware.py").write_text('''import time
from typing import Dict, List

class RateLimiter:
    """
    Sliding window rate limiter.
    TASK: Implement allow_request(client_ip: str) -> bool
    Should enforce limit from config.MAX_REQUESTS_PER_MINUTE per 60-second window.
    """

    def __init__(self, max_requests: int = 5, window_seconds: int = 60):
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self.request_history: Dict[str, List[float]] = {}

    def allow_request(self, client_ip: str) -> bool:
        now = time.time()
        if client_ip not in self.request_history:
            self.request_history[client_ip] = []
        
        # Clean timestamps older than window
        self.request_history[client_ip] = [
            t for t in self.request_history[client_ip] if now - t < self.window_seconds
        ]

        if len(self.request_history[client_ip]) < self.max_requests:
            self.request_history[client_ip].append(now)
            return True
        return False
''', encoding="utf-8")

    # app.py
    (target_dir / "app.py").write_text('''from router import OrderRouter
from middleware import RateLimiter

class ApiApp:
    def __init__(self):
        self.router = OrderRouter()
        self.limiter = RateLimiter(max_requests=5)

    def handle_request(self, client_ip: str, endpoint: str, **kwargs):
        if not self.limiter.allow_request(client_ip):
            return {"status": "error", "code": 429, "message": "Too Many Requests"}

        if endpoint == "catalog":
            return self.router.get_catalog()
        elif endpoint == "order":
            return self.router.place_order(kwargs.get("user_id"), kwargs.get("item_id"), kwargs.get("quantity", 1))
        return {"status": "error", "code": 404, "message": "Not Found"}
''', encoding="utf-8")

    # test_existing_workflow.py (Regression tests - MUST PASS)
    (target_dir / "test_existing_workflow.py").write_text('''import unittest
from app import ApiApp

class TestExistingWorkflow(unittest.TestCase):
    def setUp(self):
        self.app = ApiApp()

    def test_catalog_query(self):
        resp = self.app.handle_request("127.0.0.1", "catalog")
        self.assertIn("items", resp)

    def test_order_placement(self):
        resp = self.app.handle_request("127.0.0.1", "order", user_id="u1", item_id="item_1", quantity=2)
        self.assertEqual(resp["status"], "success")
        self.assertEqual(resp["total"], 200)

if __name__ == "__main__":
    unittest.main()
''', encoding="utf-8")

    # hidden_tests.py (Hidden evaluation tests)
    (target_dir / "hidden_tests.py").write_text('''import unittest
from app import ApiApp

class TestRateLimitingHidden(unittest.TestCase):
    def test_rate_limit_throttle(self):
        app = ApiApp()
        ip = "192.168.1.100"
        for _ in range(5):
            res = app.handle_request(ip, "catalog")
            self.assertIn("items", res)
        # 6th request must be blocked with 429
        blocked = app.handle_request(ip, "catalog")
        self.assertEqual(blocked.get("code"), 429)

if __name__ == "__main__":
    unittest.main()
''', encoding="utf-8")
