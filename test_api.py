import os
import unittest
from unittest.mock import patch

os.environ["REPOLENS_USER_KEY"] = "user-key"
os.environ["REPOLENS_ADMIN_KEY"] = "admin-key"

import psycopg
from fastapi.testclient import TestClient

import db
from server import app

db.DATABASE_URL = "dbname=repolens_test"


USER = {"X-API-Key": "user-key"}
ADMIN = {"X-API-Key": "admin-key"}


def fake_run(question, status="hypothesis"):
    return {
        "started_at": "2026-10-18T10:00:00+00:00",
        "question": question,
        "repo_dir": "/fake",
        "repo_fingerprint": "fake",
        "model": "test-model",
        "model_calls": 1,
        "tool_calls_used": 0,
        "elapsed_seconds": 0.1,
        "report": {"status": status, "evidence": []},
        "error": None,
        "trace": [],
        "usage": [],
        "run_file": f"test-{question}",
    }


def fake_agent(repo_dir, question):
    run = fake_run(question)
    run["id"] = db.insert_run(run)
    return run


class ApiTests(unittest.TestCase):
    def setUp(self):
        self.assertIn("test", db.DATABASE_URL)  # never wipe the real database
        db.init_db()
        with psycopg.connect(db.DATABASE_URL) as conn:
            conn.execute("TRUNCATE runs RESTART IDENTITY CASCADE")
        self.client = TestClient(app)

    def test_create_then_get(self):
        with patch("server.run_agent", side_effect=fake_agent):
            response = self.client.post("/api/runs", json={"question": "Why?"}, headers=USER)

        self.assertEqual(response.status_code, 201)
        run = response.json()
        self.assertEqual(run["question"], "Why?")
        self.assertEqual(response.headers["Location"], f"/api/runs/{run['id']}")

        fetched = self.client.get(response.headers["Location"])
        self.assertEqual(fetched.status_code, 200)
        self.assertEqual(fetched.json()["id"], run["id"])

    def test_create_requires_api_key(self):
        for headers in ({}, {"X-API-Key": "wrong"}):
            with self.subTest(headers=headers):
                response = self.client.post("/api/runs", json={"question": "Why?"}, headers=headers)
                self.assertEqual(response.status_code, 401)

    def test_create_rejects_bad_body(self):
        for body in ({}, {"question": "   "}, {"question": "Why?", "extra": 1}):
            with self.subTest(body=body):
                response = self.client.post("/api/runs", json=body, headers=USER)
                self.assertEqual(response.status_code, 422)

    def test_list_filters_by_status(self):
        db.insert_run(fake_run("a", "hypothesis"))
        db.insert_run(fake_run("b", "insufficient_evidence"))

        response = self.client.get("/api/runs", params={"status": "hypothesis"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual([run["question"] for run in response.json()], ["a"])

    def test_list_rejects_bad_query(self):
        for params in ({"limit": 0}, {"limit": 101}, {"status": "done"}):
            with self.subTest(params=params):
                self.assertEqual(self.client.get("/api/runs", params=params).status_code, 422)

    def test_get_missing_run(self):
        self.assertEqual(self.client.get("/api/runs/999").status_code, 404)
        self.assertEqual(self.client.get("/api/runs/abc").status_code, 422)

    def test_delete_requires_admin(self):
        run_id = db.insert_run(fake_run("a"))
        url = f"/api/runs/{run_id}"

        self.assertEqual(self.client.delete(url, headers=USER).status_code, 403)
        self.assertEqual(self.client.delete(url, headers=ADMIN).status_code, 204)
        self.assertEqual(self.client.get(url).status_code, 404)
        self.assertEqual(self.client.delete(url, headers=ADMIN).status_code, 404)

    def test_database_down(self):
        with patch("db.DATABASE_URL", "dbname=repolens_does_not_exist"):
            self.assertEqual(self.client.get("/api/runs").status_code, 503)


if __name__ == "__main__":
    unittest.main()
