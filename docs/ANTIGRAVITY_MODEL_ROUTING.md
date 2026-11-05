# Antigravity model routing for Little Dreamers

## Goal

Balance production quality and turnaround time while preserving Antigravity as the primary development workspace. Route each task to a suitable model, avoid spending premium reasoning quota on routine work, and retain a deterministic fallback path.

## Current boundary

The repository can implement a **routing policy**, but it cannot read Antigravity's private quota counters or switch the model selected in the Antigravity UI unless Antigravity exposes a supported API/CLI for those actions. The router added in `animatube.ai.model_router` is therefore deliberately explicit: the caller supplies the models currently available in the session and the quota percentages visible in the account panel. It returns a recommendation; it does not pretend to execute the model call.

Do not scrape private application state, automate hidden endpoints, store account passwords, or hardcode API keys. Do not install an unofficial provider bridge merely to bypass the quota UI.

## Task policy

| Work | Preferred model | Fallback order |
| --- | --- | --- |
| Episode story planning | Gemini Pro | Claude Sonnet, local Ollama |
| Shot and scene prompt drafting | Gemini Pro | Claude Sonnet, Gemini Flash |
| Approved-character consistency review | Gemini Pro | Claude Opus, Claude Sonnet |
| Python implementation/debugging | Claude Sonnet | GPT-OSS, Gemini Pro |
| Pipeline/root-cause debugging | Claude Sonnet | Claude Opus, Gemini Pro |
| Architecture and high-risk refactors | Claude Opus | Gemini Pro, Claude Sonnet |
| Technical QA analysis | Claude Sonnet | Claude Opus, Gemini Pro |
| Titles, descriptions and routine text | Gemini Flash | GPT-OSS, local Ollama |

The six approved Little Dreamers character references remain locked. A model may inspect and compare generated frames against those references, but must not redesign or regenerate the approved character designs unless the creator explicitly asks.

## Quota guardrails

- Treat Gemini Flash and Gemini Pro as one shared quota group.
- Treat Claude Opus, Claude Sonnet and GPT-OSS as one shared quota group.
- Start switching away from a group when weekly remaining is at or below 10%, or five-hour remaining is at or below 5%.
- Unknown quota is not the same as exhausted quota. Never infer a quota percentage.
- Refresh the quota snapshot before a long batch; do not assume the value remains current.
- Keep Opus for architecture, difficult root causes and final independent review—not routine copy edits.
- Local Ollama is a local fallback for structured drafts, not a substitute for high-quality visual review.

## Speed without quality loss

1. Freeze the approved story, character references, storyboard and shot prompts before rendering.
2. Fingerprint each scene's source prompt, references, voice, render settings and tool/model version.
3. Reuse a cached scene only when the full fingerprint matches; invalidate only affected scenes.
4. Run independent scene preparation and audio generation concurrently only where the existing renderer/provider is thread-safe and hardware capacity permits.
5. Keep GPU-heavy rendering bounded by a configurable worker limit to avoid memory pressure and slower total throughput.
6. Render a low-cost preview first; approve framing, character identity, motion and audio before the full-resolution batch.
7. Run automated checks on every scene, then inspect the final assembled video and audio manually.

## Quality gates

A render is not complete merely because a process exits successfully. Require:
- expected output file exists and is non-empty;
- ffprobe confirms codec, 1920x1080, 24 fps and expected duration;
- audio is present, audible, correctly synchronized and not clipped;
- subtitles match the approved dialogue and timing;
- generated frames preserve the six approved character designs;
- no black frames, missing assets, abrupt cuts or corrupted scenes;
- human review approves the complete episode before publication.

Never publish automatically. Keep the creator's final approval gate.

## Example policy usage

```python
from animatube.ai.model_router import ModelGroup, ModelQuota, ModelRouter, ProductionTask

decision = ModelRouter().select(
    ProductionTask.PIPELINE_DEBUGGING,
    available_models={"claude_sonnet", "claude_opus", "gemini_pro", "gpt_oss"},
    quotas={
        ModelGroup.GEMINI: ModelQuota(weekly_remaining=45.38, five_hour_remaining=95.02),
        ModelGroup.CLAUDE_GPT: ModelQuota(weekly_remaining=100, five_hour_remaining=100),
    },
)
print(decision.model_id, decision.reason)
```

The example consumes no model quota. It only chooses a route from the supplied snapshot.
