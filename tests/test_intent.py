from __future__ import annotations

import json
import os
import unittest
from pathlib import Path
from unittest.mock import patch

from app.ai.intent import LLMIntentClient, classify_intent_locally
from app.ai.llm import LLMClientConfig
from app.config import get_settings


class IntentClassifierTest(unittest.TestCase):
    def test_30_fixture_samples_reach_threshold(self) -> None:
        samples = json.loads(Path("tests/fixtures/intent_samples.json").read_text(encoding="utf-8"))
        correct = 0
        failures: list[tuple[str, str, str]] = []
        for sample in samples:
            result = classify_intent_locally(sample["text"])
            if result.intent == sample["intent"]:
                correct += 1
            else:
                failures.append((sample["text"], sample["intent"], result.intent))
        self.assertGreaterEqual(correct, 27, failures)

    def test_llm_client_parses_structured_output(self) -> None:
        client = LLMIntentClient(
            config=LLMClientConfig(
                provider="test",
                api_key="",
                model="test-model",
                base_url="https://llm.example.com/v1",
                responses_path="/responses",
                timeout_seconds=1,
            ),
            transport=lambda _body: {
                "output_text": json.dumps(
                    {
                        "intent": "todo.create",
                        "confidence": 0.9,
                        "fields": {"todo_title": "交房租"},
                        "missing_fields": [],
                        "reply": "已识别待办",
                    }
                )
            },
        )
        result = client.parse("明天提醒我交房租")
        self.assertEqual(result.intent, "todo.create")
        self.assertEqual(result.fields["todo_title"], "交房租")

    def test_llm_config_can_fallback_to_legacy_openai_env(self) -> None:
        get_settings.cache_clear()
        with patch.dict(
            os.environ,
            {
                "OPENAI_API_KEY": "legacy-key",
                "OPENAI_MODEL": "legacy-model",
                "OPENAI_BASE_URL": "https://legacy.example.com/v1",
                "OPENAI_TIMEOUT_SECONDS": "9",
            },
            clear=True,
        ):
            settings = get_settings()
        get_settings.cache_clear()

        self.assertEqual(settings.llm_api_key, "legacy-key")
        self.assertEqual(settings.llm_model, "legacy-model")
        self.assertEqual(settings.llm_base_url, "https://legacy.example.com/v1")
        self.assertEqual(settings.llm_timeout_seconds, 9)

    def test_clarify_reply_is_a_question(self) -> None:
        result = classify_intent_locally("明天提醒我")
        self.assertEqual(result.intent, "clarify")
        self.assertIn("提醒什么", result.reply)


if __name__ == "__main__":
    unittest.main()
