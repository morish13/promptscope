import os
import json
import random
import hashlib
import httpx
from dataclasses import dataclass

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
MODEL = "claude-sonnet-4-20250514"
MOCK_MODE = os.getenv("PROMPTSCOPE_MOCK", "0") == "1"

SCORE_SYSTEM = """You are a prompt quality evaluator. Given a prompt, score it on these 5 dimensions (each 1-10):

1. clarity - Is the instruction unambiguous? Does the model know exactly what to do?
2. specificity - Does it give enough context, constraints, format expectations?
3. goal_alignment - Is the stated goal achievable from this prompt alone?
4. instruction_following_likelihood - How likely is a model to follow this correctly on first try?
5. ambiguity_risk - Inverse score: 10 = no ambiguity, 1 = highly ambiguous

Return ONLY valid JSON in this exact shape, no extra text:
{
  "scores": {
    "clarity": <int>,
    "specificity": <int>,
    "goal_alignment": <int>,
    "instruction_following_likelihood": <int>,
    "ambiguity_risk": <int>
  },
  "overall": <float, average of above>,
  "strengths": [<str>, ...],
  "weaknesses": [<str>, ...],
  "rewrite_suggestion": "<improved version of the prompt>"
}"""


@dataclass
class ScoreResult:
    scores: dict
    overall: float
    strengths: list
    weaknesses: list
    rewrite_suggestion: str
    raw_prompt: str


def _call_api(messages: list, system: str = None) -> str:
    payload = {
        "model": MODEL,
        "max_tokens": 1500,
        "messages": messages,
    }
    if system:
        payload["system"] = system

    headers = {
        "x-api-key": ANTHROPIC_API_KEY,
        "anthropic-version": "2023-06-01",
        "content-type": "application/json",
    }

    r = httpx.post(
        "https://api.anthropic.com/v1/messages",
        json=payload,
        headers=headers,
        timeout=30,
    )
    r.raise_for_status()
    data = r.json()
    return data["content"][0]["text"]


def _mock_score(prompt: str) -> "ScoreResult":
    seed = int(hashlib.md5(prompt.encode()).hexdigest()[:8], 16)
    rng = random.Random(seed)

    words = prompt.split()
    has_format = any(w in prompt.lower() for w in ["json", "list", "bullet", "format", "return", "output"])
    has_context = len(words) > 15
    has_examples = "example" in prompt.lower() or "e.g" in prompt.lower()
    is_vague = len(words) < 8

    clarity = rng.randint(5, 9) + (1 if not is_vague else -2)
    specificity = rng.randint(4, 8) + (2 if has_format else 0) + (1 if has_context else 0)
    goal_alignment = rng.randint(5, 9)
    ifl = rng.randint(4, 9) + (1 if has_examples else 0)
    ambiguity = rng.randint(4, 9) - (2 if is_vague else 0)

    def clamp(v): return max(1, min(10, v))
    scores = {
        "clarity": clamp(clarity),
        "specificity": clamp(specificity),
        "goal_alignment": clamp(goal_alignment),
        "instruction_following_likelihood": clamp(ifl),
        "ambiguity_risk": clamp(ambiguity),
    }
    overall = round(sum(scores.values()) / len(scores), 1)

    strengths = []
    weaknesses = []
    if scores["clarity"] >= 7:
        strengths.append("Instruction is clear and direct")
    else:
        weaknesses.append("Instruction is vague or ambiguous")
    if has_format:
        strengths.append("Output format is specified")
    else:
        weaknesses.append("No output format specified")
    if has_examples:
        strengths.append("Includes examples to guide the model")
    else:
        weaknesses.append("No examples provided")
    if has_context:
        strengths.append("Sufficient context given")
    else:
        weaknesses.append("More context would help")

    rewrite = f"{prompt.rstrip('.')}. Return the result as a structured list. Include at least one example to clarify expected output."

    return ScoreResult(
        scores=scores,
        overall=overall,
        strengths=strengths,
        weaknesses=weaknesses,
        rewrite_suggestion=rewrite,
        raw_prompt=prompt,
    )


def _mock_compare(prompt_a: str, prompt_b: str) -> dict:
    score_a = len(prompt_a.split()) + prompt_a.lower().count("format") * 3
    score_b = len(prompt_b.split()) + prompt_b.lower().count("format") * 3
    if score_a > score_b:
        winner, reason = "A", "Prompt A is more detailed and specific"
    elif score_b > score_a:
        winner, reason = "B", "Prompt B is more detailed and specific"
    else:
        winner, reason = "tie", "Both prompts are roughly equivalent in quality"
    return {
        "winner": winner,
        "reasoning": reason,
        "a_advantages": ["More words = more context", "Clearer intent"],
        "b_advantages": ["More concise", "Less risk of overspecification"],
    }


def score_prompt(prompt: str) -> ScoreResult:
    if MOCK_MODE:
        return _mock_score(prompt)

    msg = [{"role": "user", "content": f"Evaluate this prompt:\n\n{prompt}"}]
    raw = _call_api(msg, system=SCORE_SYSTEM)

    clean = raw.strip()
    if clean.startswith("```"):
        clean = clean.split("```")[1]
        if clean.startswith("json"):
            clean = clean[4:]
    clean = clean.strip()

    parsed = json.loads(clean)

    return ScoreResult(
        scores=parsed["scores"],
        overall=parsed["overall"],
        strengths=parsed.get("strengths", []),
        weaknesses=parsed.get("weaknesses", []),
        rewrite_suggestion=parsed.get("rewrite_suggestion", ""),
        raw_prompt=prompt,
    )


def compare_prompts(prompt_a: str, prompt_b: str) -> dict:
    if MOCK_MODE:
        return _mock_compare(prompt_a, prompt_b)

    system = """You are a prompt quality evaluator. Compare two prompts and determine which is better and why.
Return ONLY valid JSON:
{
  "winner": "A" or "B" or "tie",
  "reasoning": "<why>",
  "a_advantages": [<str>, ...],
  "b_advantages": [<str>, ...]
}"""

    content = f"Prompt A:\n{prompt_a}\n\nPrompt B:\n{prompt_b}"
    msg = [{"role": "user", "content": content}]
    raw = _call_api(msg, system=system)

    clean = raw.strip()
    if clean.startswith("```"):
        clean = clean.split("```")[1]
        if clean.startswith("json"):
            clean = clean[4:]

    return json.loads(clean.strip())
