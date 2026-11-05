from __future__ import annotations

import unittest

from animatube.ai.model_router import (
    ModelGroup,
    ModelQuota,
    ModelRouter,
    NoAvailableModelError,
    ProductionTask,
)


class ModelRouterTests(unittest.TestCase):
    def setUp(self) -> None:
        self.router = ModelRouter()

    def test_uses_task_specific_quality_first_route(self) -> None:
        decision = self.router.select(
            ProductionTask.ARCHITECTURE,
            available_models={"claude_opus", "gemini_pro", "claude_sonnet"},
        )
        self.assertEqual(decision.model_id, "claude_opus")
        self.assertEqual(decision.group, ModelGroup.CLAUDE_GPT)

    def test_skips_gemini_when_weekly_quota_is_at_threshold(self) -> None:
        decision = self.router.select(
            ProductionTask.STORY_PLANNING,
            available_models={"gemini_pro", "claude_sonnet", "ollama_local"},
            quotas={ModelGroup.GEMINI: ModelQuota(weekly_remaining=10.0, five_hour_remaining=90.0)},
        )
        self.assertEqual(decision.model_id, "claude_sonnet")
        self.assertIn("fallback", decision.reason.lower())

    def test_skips_group_when_five_hour_quota_is_low(self) -> None:
        decision = self.router.select(
            ProductionTask.PYTHON_DEBUGGING,
            available_models={"claude_sonnet", "gpt_oss", "gemini_pro"},
            quotas={ModelGroup.CLAUDE_GPT: ModelQuota(weekly_remaining=90.0, five_hour_remaining=4.0)},
        )
        self.assertEqual(decision.model_id, "gemini_pro")

    def test_does_not_claim_unavailable_fallback_exists(self) -> None:
        with self.assertRaises(NoAvailableModelError):
            self.router.select(
                ProductionTask.ARCHITECTURE,
                available_models=set(),
            )

    def test_preferred_model_is_respected_when_available_and_quota_ok(self) -> None:
        decision = self.router.select(
            ProductionTask.METADATA,
            available_models={"claude_opus", "gemini_flash"},
            preferred_model="claude_opus",
        )
        self.assertEqual(decision.model_id, "claude_opus")

    def test_unknown_preferred_model_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            self.router.select(
                ProductionTask.METADATA,
                available_models={"gemini_flash"},
                preferred_model="made_up_model",
            )

    def test_unknown_quota_does_not_block_a_model(self) -> None:
        decision = self.router.select(
            ProductionTask.METADATA,
            available_models={"gemini_flash"},
            quotas={ModelGroup.GEMINI: ModelQuota()},
        )
        self.assertEqual(decision.model_id, "gemini_flash")

    def test_local_model_is_not_blocked_by_cloud_quota(self) -> None:
        decision = self.router.select(
            ProductionTask.ROUTINE_TEXT,
            available_models={"gemini_flash", "ollama_local"},
            quotas={ModelGroup.GEMINI: ModelQuota(weekly_remaining=0, five_hour_remaining=0)},
        )
        self.assertEqual(decision.model_id, "ollama_local")


if __name__ == "__main__":
    unittest.main()
