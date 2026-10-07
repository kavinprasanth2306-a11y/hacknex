"""Benchmark scenario 1: Auth & Token Session Bugfix."""

import os
from pathlib import Path

def setup_auth_repo(target_dir: Path):
    """Generates a complete Python microservice repository with a documented auth session bug."""
    target_dir.mkdir(parents=True, exist_ok=True)
    
    # 1. auth_service.py with the documented bug
    (target_dir / "auth_service.py").write_text('''import time
from typing import Dict, Optional

class TokenManager:
    """Manages authentication tokens, validation, and session refresh."""

    def __init__(self, default_ttl_seconds: int = 300):
        self.default_ttl = default_ttl_seconds
        self.sessions: Dict[str, Dict] = {}

    def create_session(self, user_id: str, username: str) -> str:
        token = f"tok_{user_id}_{int(time.time() * 1000)}"
        expires_at = time.time() + self.default_ttl
        self.sessions[token] = {
            "user_id": user_id,
            "username": username,
            "expires_at": expires_at,
            "is_revoked": False
        }
        return token

    def validate_token(self, token: str) -> Optional[Dict]:
        """Validate token and return session payload if valid."""
        session = self.sessions.get(token)
        if not session or session["is_revoked"]:
            return None
            
        current_time = time.time()
        # BUG: The boundary condition has an erroneous strict comparison '>'
        # and doesn't handle refreshed timestamps correctly when refreshed right at expiration
        if current_time >= session["expires_at"]:
            return None
            
        return session

    def refresh_session(self, old_token: str) -> Optional[str]:
        """
        Refresh an active session by issuing a new token and extending TTL.
        BUG: Erroneously mutates the old token in-place and sets an expired timestamp,
        violating token rotation and causing refreshed sessions to fail validation.
        """
        session = self.sessions.get(old_token)
        if not session or session["is_revoked"]:
            return None

        # Buggy implementation: fails to issue new token and sets expired timestamp
        session["expires_at"] = time.time() - 10
        return old_token

    def revoke_session(self, token: str) -> bool:
        if token in self.sessions:
            self.sessions[token]["is_revoked"] = True
            return True
        return False
''', encoding="utf-8")

    # 2. Existing working tests (Regression Guard - MUST PASS)
    (target_dir / "test_auth_baseline.py").write_text('''import unittest
from auth_service import TokenManager

class TestAuthBaseline(unittest.TestCase):
    """Existing regression tests that MUST CONTINUE TO PASS."""

    def setUp(self):
        self.mgr = TokenManager(default_ttl_seconds=300)

    def test_create_and_validate_session(self):
        token = self.mgr.create_session("u123", "alice")
        session = self.mgr.validate_token(token)
        self.assertIsNotNone(session)
        self.assertEqual(session["username"], "alice")

    def test_revocation(self):
        token = self.mgr.create_session("u456", "bob")
        self.assertTrue(self.mgr.revoke_session(token))
        self.assertIsNone(self.mgr.validate_token(token))

    def test_invalid_token(self):
        self.assertIsNone(self.mgr.validate_token("nonexistent_tok"))

if __name__ == "__main__":
    unittest.main()
''', encoding="utf-8")

    # 3. Acceptance test for the bug (Fails before fix, passes after fix)
    (target_dir / "test_token_refresh.py").write_text('''import unittest
import time
from auth_service import TokenManager

class TestTokenRefresh(unittest.TestCase):
    """Acceptance test: Refresh active session without losing identity or breaking validation."""

    def test_refresh_active_session(self):
        mgr = TokenManager(default_ttl_seconds=10)
        old_token = mgr.create_session("u789", "charlie")
        
        # Refresh session
        new_token = mgr.refresh_session(old_token)
        self.assertIsNotNone(new_token, "Refreshed token must not be None")
        self.assertNotEqual(old_token, new_token, "Refreshed token must be distinct")

        # Validate old token is now invalid
        self.assertIsNone(mgr.validate_token(old_token), "Old token must be revoked")

        # Validate new token is valid and carries user metadata
        new_session = mgr.validate_token(new_token)
        self.assertIsNotNone(new_session, "New token must be valid")
        self.assertEqual(new_session["username"], "charlie")
        self.assertEqual(new_session["user_id"], "u789")

if __name__ == "__main__":
    unittest.main()
''', encoding="utf-8")

    # 4. Hidden test suite (used by benchmark scorer for 30 points)
    (target_dir / "hidden_tests.py").write_text('''import unittest
import time
from auth_service import TokenManager

class HiddenTestSuite(unittest.TestCase):
    """Hidden evaluation test suite to judge hidden test correctness (30 points)."""

    def test_rapid_sequential_refreshes(self):
        mgr = TokenManager(default_ttl_seconds=50)
        tok = mgr.create_session("u999", "dana")
        for _ in range(5):
            next_tok = mgr.refresh_session(tok)
            self.assertIsNotNone(next_tok)
            self.assertIsNone(mgr.validate_token(tok))
            tok = next_tok
        session = mgr.validate_token(tok)
        self.assertIsNotNone(session)
        self.assertEqual(session["username"], "dana")

    def test_cannot_refresh_revoked_session(self):
        mgr = TokenManager(default_ttl_seconds=50)
        tok = mgr.create_session("u888", "eve")
        mgr.revoke_session(tok)
        self.assertIsNone(mgr.refresh_session(tok))

if __name__ == "__main__":
    unittest.main()
''', encoding="utf-8")
