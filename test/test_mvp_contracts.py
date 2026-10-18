"""Offline contract tests for the B 档 MVP (no API calls)."""
from __future__ import annotations

import json
import pathlib
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from app.crewai_bootstrap import bootstrap_crewai

bootstrap_crewai()

from crewai.tasks.task_output import TaskOutput  # noqa: E402

from app.mvp_crew import (  # noqa: E402
    _json_text,
    validate_itinerary,
    validate_profiles,
    validate_research,
)


def task_output(raw: str) -> TaskOutput:
    return TaskOutput(description="test", raw=raw, agent="test")


class TestJsonText(unittest.TestCase):
    def test_plain_json(self):
        self.assertEqual(_json_text('{"a": 1}'), '{"a": 1}')

    def test_markdown_fence(self):
        self.assertEqual(_json_text('```json\n{"a": 1}\n```'), '{"a": 1}')

    def test_prose_around_json(self):
        self.assertEqual(_json_text('结果如下：{"a": 1} 完毕'), '{"a": 1}')


class TestGuardrails(unittest.TestCase):
    def test_profile_count(self):
        one = {
            "profiles": [
                {"user_id": "u1", "summary": "安静", "interests": []},
            ]
        }
        ok, _ = validate_profiles(2)(task_output(json.dumps(one, ensure_ascii=False)))
        self.assertFalse(ok)

        two = {
            "profiles": [
                {"user_id": "u1", "summary": "安静", "interests": []},
                {"user_id": "u2", "summary": "热闹", "interests": []},
            ]
        }
        ok, _ = validate_profiles(2)(task_output(json.dumps(two, ensure_ascii=False)))
        self.assertTrue(ok)

    def test_research_min_activities(self):
        data = {"destination": "大理", "activities": []}
        ok, _ = validate_research(6)(task_output(json.dumps(data, ensure_ascii=False)))
        self.assertFalse(ok)

    def test_itinerary_empty_day(self):
        data = {"destination": "大理", "days": [{"day": 1, "items": []}]}
        ok, _ = validate_itinerary(1)(task_output(json.dumps(data, ensure_ascii=False)))
        self.assertFalse(ok)


if __name__ == "__main__":
    unittest.main(verbosity=2)
