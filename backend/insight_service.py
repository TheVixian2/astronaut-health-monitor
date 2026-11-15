# Written with AI assistance (Claude Code, Anthropic) and reviewed by the team. See README "Use of AI".
"""Claude insight service: explains a newly matched condition to the astronaut.

Called only when a condition NEWLY matches (the condition engine gates it).
Never raises into the request path: a missing ANTHROPIC_API_KEY, a timeout, a
refusal or any other failure returns the fallback Insight, so the demo never
breaks.

Try it:  python insight_service.py   (prints one insight for a sample alert)
"""

import asyncio
import json
import logging
import os
from pathlib import Path
from typing import Optional

import anthropic
from pydantic import BaseModel

log = logging.getLogger("insight_service")

MODEL = os.getenv("INSIGHT_MODEL", "claude-sonnet-5-5")  # claude-haiku-5-5 for speed
TIMEOUT_S = float(os.getenv("INSIGHT_TIMEOUT_S", "20"))


class Insight(BaseModel):
    why: str
    trend: str
    recommended_action: str


GENERIC_FALLBACK = Insight(
    why="A pattern in your vitals differs from your personal baseline.",
    trend="See the chart for how your values moved compared with your usual range.",
    recommended_action="Follow the on-board action shown for this alert and re-check soon. "
                       "If you feel unwell, tell the Crew Medical Officer.",
)

SYSTEM_PROMPT = """You support an astronaut on a long-duration mission who is checking their own health.
You get one alert that a monitoring system just raised: the condition profile, the astronaut's
current vitals, their personal baseline (measured on mission days 7-14), the pre-written on-board
action, and the communication delay to Earth.

Write three short fields, each one or two plain-language sentences for a non-doctor:
- why: what pattern triggered the alert and why it matters in spaceflight.
- trend: how the values compare with THIS astronaut's own baseline, using the numbers given.
- recommended_action: what to do now. Stay consistent with the on-board action and expand on it.
  If ground_will_see_in_time is false, the astronaut must act on board without waiting for Houston.

Rules: decision support only, never a diagnosis. Use suggestive wording ("may suggest", "worth
checking"), not clinical certainty. Use only the numbers provided; do not invent readings."""


def _load_dotenv() -> None:
    # Minimal .env loader (no extra dependency); real environment variables win.
    env = Path(__file__).with_name(".env")
    if not env.exists():
        return
    for line in env.read_text(encoding="utf-8").splitlines():
        key, sep, value = line.strip().partition("=")
        if sep and key and not key.startswith("#"):
            os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


_load_dotenv()
_client: Optional[anthropic.AsyncAnthropic] = None


def _get_client() -> Optional[anthropic.AsyncAnthropic]:
    global _client
    if _client is None and os.getenv("ANTHROPIC_API_KEY"):
        # One retry only: a slow insight is fine, a hanging one is not.
        _client = anthropic.AsyncAnthropic(timeout=TIMEOUT_S, max_retries=1)
    return _client


async def generate_insight(
    profile: str,
    vitals: dict,
    baseline: dict,
    *,
    onboard_action: str,
    act_within_s: int,
    one_way_delay_s: int,
    fallback: Optional[Insight] = None,
) -> Insight:
    """Return Claude's Insight for a newly matched condition, or `fallback` on any failure."""
    fallback = fallback or GENERIC_FALLBACK
    client = _get_client()
    if client is None:
        return fallback

    round_trip_s = 2 * one_way_delay_s
    case = {
        "condition_profile": profile,
        "current_vitals": vitals,
        "personal_baseline": baseline,
        "onboard_action": onboard_action,
        "act_within_s": act_within_s,
        "round_trip_to_ground_s": round_trip_s,
        "ground_will_see_in_time": round_trip_s <= act_within_s,
    }
    try:
        response = await client.beta.messages.parse(
            model=MODEL,
            max_tokens=16000,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": json.dumps(case, default=str)}],
            output_format=Insight,
            output_config={"effort": "low"},  # three short sentences; keep latency down
            # On a policy decline, the API retries on a fallback model in the same call.
            betas=["server-side-fallback-2026-07-01"],
            fallbacks="default",
        )
    except anthropic.APITimeoutError:
        log.warning("Insight timed out after %ss; using fallback", TIMEOUT_S)
        return fallback
    except anthropic.APIConnectionError as e:
        log.warning("Insight connection error (%s); using fallback", e)
        return fallback
    except anthropic.RateLimitError:
        log.warning("Insight rate limited; using fallback")
        return fallback
    except anthropic.APIStatusError as e:
        log.warning("Insight API error %s: %s; using fallback", e.status_code, e.message)
        return fallback
    except Exception:
        log.exception("Insight failed unexpectedly; using fallback")
        return fallback

    if response.stop_reason == "refusal" or response.parsed_output is None:
        log.warning("Insight not usable (stop_reason=%s); using fallback", response.stop_reason)
        return fallback
    return response.parsed_output


ASK_SYSTEM = """You answer an astronaut's question on their smartwatch during a long Mars mission.
You get the question and a JSON snapshot: their current physical readings, their personal baseline
(mission days 7-14), the live cabin air, and the light-time delay to Earth.

Answer in at most three short sentences that fit a watch screen, in plain language, using only the
numbers given. Compare with THEIR baseline, not population norms. Decision support only: never a
diagnosis; use suggestive wording ("may", "worth"). If something sounds urgent, say to act on board
and tell the Crew Medical Officer, because Mission Control is too far away to answer in time.
You have no data on mood or mental health: if asked about it, say the Crew Medical Officer or a private
conference is the right place, and do not guess."""


async def answer_question(question: str, context: dict, fallback: str) -> tuple[str, str]:
    """Answer a watch question with Claude. Returns (answer, source): source is "claude" or "on_board".

    Only physical readings, cabin air and mission state are sent: never mood or questionnaire answers.
    Any failure (no key, timeout, refusal, API error) returns the on-board `fallback` text instead.
    """
    client = _get_client()
    if client is None:
        return fallback, "on_board"
    try:
        response = await client.beta.messages.create(
            model=MODEL,
            max_tokens=16000,
            system=ASK_SYSTEM,
            messages=[{"role": "user", "content": json.dumps({"question": question, "data": context}, default=str)}],
            output_config={"effort": "low"},  # three sentences on a watch; keep latency down
            # On a policy decline, the API retries on a fallback model in the same call.
            betas=["server-side-fallback-2026-07-01"],
            fallbacks="default",
        )
    except anthropic.APITimeoutError:
        log.warning("Ask timed out after %ss; on-board answer", TIMEOUT_S)
        return fallback, "on_board"
    except anthropic.APIConnectionError as e:
        log.warning("Ask connection error (%s); on-board answer", e)
        return fallback, "on_board"
    except anthropic.RateLimitError:
        log.warning("Ask rate limited; on-board answer")
        return fallback, "on_board"
    except anthropic.APIStatusError as e:
        log.warning("Ask API error %s: %s; on-board answer", e.status_code, e.message)
        return fallback, "on_board"
    except Exception:
        log.exception("Ask failed unexpectedly; on-board answer")
        return fallback, "on_board"
    text = "".join(b.text for b in response.content if b.type == "text").strip()
    if response.stop_reason == "refusal" or not text:
        log.warning("Ask not usable (stop_reason=%s); on-board answer", response.stop_reason)
        return fallback, "on_board"
    return text, "claude"


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    sample = asyncio.run(generate_insight(
        "sleep_debt",
        vitals={"heart_rate_bpm": 66, "sleep_h_last_night": 5.0, "mood_1to5": 2},
        baseline={"heart_rate_bpm": 58, "sleep_h_last_night": 7.2, "mood_1to5": 4},
        onboard_action="Consider pre-sleep lighting (2700K) 1 h before bed, screens aside, eye mask.",
        act_within_s=86400,
        one_way_delay_s=780,
    ))
    print(f"model={MODEL} key_set={bool(os.getenv('ANTHROPIC_API_KEY'))}")
    print(sample.model_dump_json(indent=2))
