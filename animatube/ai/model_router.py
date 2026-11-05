from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Iterable, Mapping


class ModelGroup(str, Enum):
    GEMINI = "gemini"
    CLAUDE_GPT = "claude_gpt"
    LOCAL = "local"


class ProductionTask(str, Enum):
    STORY_PLANNING = "story_planning"
    SHOT_PROMPTING = "shot_prompting"
    CHARACTER_CONSISTENCY_REVIEW = "character_consistency_review"
    PYTHON_DEBUGGING = "python_debugging"
    PIPELINE_DEBUGGING = "pipeline_debugging"
    ARCHITECTURE = "architecture"
    QA_ANALYSIS = "qa_analysis"
    METADATA = "metadata"
    ROUTINE_TEXT = "routine_text"


@dataclass(frozen=True)
class ModelQuota:
    """Observed quota percentages for a shared model group; None means unknown."""

    weekly_remaining: float | None = None
    five_hour_remaining: float | None = None

    def __post_init__(self) -> None:
        for label, value in (
            ("weekly_remaining", self.weekly_remaining),
            ("five_hour_remaining", self.five_hour_remaining),
        ):
            if value is not None and not 0.0 <= value <= 100.0:
                raise ValueError(f"{label} must be between 0 and 100")


@dataclass(frozen=True)
class ModelCandidate:
    model_id: str
    group: ModelGroup
    quality_tier: int
    speed_tier: int


@dataclass(frozen=True)
class ModelDecision:
    task: ProductionTask
    model_id: str
    group: ModelGroup
    reason: str
    fallback_candidates: tuple[str, ...]


# IDs are stable internal labels, not API model identifiers. The Antigravity
# adapter/UI must map them to models actually exposed by the user's account.
MODEL_CATALOG: dict[str, ModelCandidate] = {
    "gemini_flash": ModelCandidate("gemini_flash", ModelGroup.GEMINI, 2, 5),
    "gemini_pro": ModelCandidate("gemini_pro", ModelGroup.GEMINI, 4, 3),
    "claude_sonnet": ModelCandidate("claude_sonnet", ModelGroup.CLAUDE_GPT, 4, 4),
    "claude_opus": ModelCandidate("claude_opus", ModelGroup.CLAUDE_GPT, 5, 2),
    "gpt_oss": ModelCandidate("gpt_oss", ModelGroup.CLAUDE_GPT, 2, 4),
    "ollama_local": ModelCandidate("ollama_local", ModelGroup.LOCAL, 2, 3),
}

# Ordered by intended quality/speed balance. The router never invents a model
# or calls a provider; it selects only from explicitly available model IDs.
TASK_ROUTES: dict[ProductionTask, tuple[str, ...]] = {
    ProductionTask.STORY_PLANNING: ("gemini_pro", "claude_sonnet", "ollama_local"),
    ProductionTask.SHOT_PROMPTING: ("gemini_pro", "claude_sonnet", "gemini_flash"),
    ProductionTask.CHARACTER_CONSISTENCY_REVIEW: ("gemini_pro", "claude_opus", "claude_sonnet"),
    ProductionTask.PYTHON_DEBUGGING: ("claude_sonnet", "gpt_oss", "gemini_pro"),
    ProductionTask.PIPELINE_DEBUGGING: ("claude_sonnet", "claude_opus", "gemini_pro"),
    ProductionTask.ARCHITECTURE: ("claude_opus", "gemini_pro", "claude_sonnet"),
    ProductionTask.QA_ANALYSIS: ("claude_sonnet", "claude_opus", "gemini_pro"),
    ProductionTask.METADATA: ("gemini_flash", "gpt_oss", "claude_sonnet"),
    ProductionTask.ROUTINE_TEXT: ("gemini_flash", "gpt_oss", "ollama_local"),
}


class NoAvailableModelError(RuntimeError):
    """No configured, available model remains for the requested task."""


def _quota_is_low(
    quota: ModelQuota | None,
    *,
    weekly_threshold: float,
    five_hour_threshold: float,
) -> bool:
    if quota is None:
        return False
    return (
        (quota.weekly_remaining is not None and quota.weekly_remaining <= weekly_threshold)
        or (quota.five_hour_remaining is not None and quota.five_hour_remaining <= five_hour_threshold)
    )


class ModelRouter:
    """Quota-aware model selection policy for Antigravity-assisted production.

    Pass a fresh set of model IDs visible in Antigravity and quota observations
    copied from the account's quota panel. This class does not scrape quota,
    authenticate to Antigravity, or execute model requests.
    """

    def __init__(
        self,
        *,
        routes: Mapping[ProductionTask, tuple[str, ...]] | None = None,
        weekly_switch_threshold: float = 10.0,
        five_hour_switch_threshold: float = 5.0,
    ) -> None:
        if not 0 <= weekly_switch_threshold <= 100:
            raise ValueError("weekly_switch_threshold must be between 0 and 100")
        if not 0 <= five_hour_switch_threshold <= 100:
            raise ValueError("five_hour_switch_threshold must be between 0 and 100")
        self.routes = dict(routes or TASK_ROUTES)
        self.weekly_switch_threshold = weekly_switch_threshold
        self.five_hour_switch_threshold = five_hour_switch_threshold

    def select(
        self,
        task: ProductionTask,
        *,
        available_models: Iterable[str],
        quotas: Mapping[ModelGroup, ModelQuota] | None = None,
        preferred_model: str | None = None,
    ) -> ModelDecision:
        available = set(available_models)
        if preferred_model:
            if preferred_model not in MODEL_CATALOG:
                raise ValueError(f"Unknown model label: {preferred_model}")
            ordered = (preferred_model,) + tuple(
                model for model in self.routes.get(task, ()) if model != preferred_model
            )
        else:
            ordered = self.routes.get(task, ())
        if not ordered:
            raise ValueError(f"No routing policy configured for task: {task.value}")

        quota_map = quotas or {}
        skipped: list[str] = []
        for model_id in ordered:
            candidate = MODEL_CATALOG.get(model_id)
            if candidate is None:
                continue
            if model_id not in available:
                skipped.append(f"{model_id} is not available in this Antigravity session")
                continue

            quota = quota_map.get(candidate.group)
            low = _quota_is_low(
                quota,
                weekly_threshold=self.weekly_switch_threshold,
                five_hour_threshold=self.five_hour_switch_threshold,
            )
            if low and candidate.group is not ModelGroup.LOCAL:
                skipped.append(f"{model_id} skipped because {candidate.group.value} quota is at the switch threshold")
                continue

            if skipped:
                reason = "Selected after fallback: " + "; ".join(skipped)
            elif preferred_model == model_id:
                reason = "Selected because it is the available preferred model and its known quota is above the switch threshold."
            else:
                reason = "Selected by the task's quality/speed routing policy; availability and known quota checks passed."
            fallbacks = tuple(
                other for other in ordered
                if other != model_id and other in available and other in MODEL_CATALOG
                and not (
                    MODEL_CATALOG[other].group is not ModelGroup.LOCAL
                    and _quota_is_low(
                        quota_map.get(MODEL_CATALOG[other].group),
                        weekly_threshold=self.weekly_switch_threshold,
                        five_hour_threshold=self.five_hour_switch_threshold,
                    )
                )
            )
            return ModelDecision(task, model_id, candidate.group, reason, fallbacks)

        raise NoAvailableModelError(
            f"No available model for task '{task.value}'. "
            f"Available models: {', '.join(sorted(available)) or 'none'}. "
            f"Skipped: {'; '.join(skipped) or 'no route candidates configured'}."
        )
