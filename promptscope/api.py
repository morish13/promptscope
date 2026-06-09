from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional
import os

from promptscope.scorer import score_prompt, compare_prompts
from promptscope.db import save_result, get_history, get_by_id, delete_record

app = FastAPI(
    title="promptscope",
    description="Score, analyze, and improve LLM prompts via API",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


class ScoreRequest(BaseModel):
    prompt: str
    mock: bool = False
    save: bool = True


class CompareRequest(BaseModel):
    prompt_a: str
    prompt_b: str
    mock: bool = False


class ScoreResponse(BaseModel):
    id: Optional[int] = None
    prompt: str
    scores: dict
    overall: float
    strengths: list
    weaknesses: list
    rewrite_suggestion: str


class CompareResponse(BaseModel):
    winner: str
    reasoning: str
    a_advantages: list
    b_advantages: list


@app.get("/", tags=["meta"])
def root():
    return {"name": "promptscope", "version": "0.1.0", "docs": "/docs"}


@app.post("/score", response_model=ScoreResponse, tags=["scoring"])
def score(req: ScoreRequest):
    if req.mock:
        os.environ["PROMPTSCOPE_MOCK"] = "1"
    else:
        os.environ["PROMPTSCOPE_MOCK"] = "0"

    import importlib
    import promptscope.scorer as sc
    importlib.reload(sc)

    if not req.prompt.strip():
        raise HTTPException(status_code=422, detail="prompt cannot be empty")

    result = sc.score_prompt(req.prompt)

    rid = None
    if req.save:
        rid = save_result(result)

    return ScoreResponse(
        id=rid,
        prompt=result.raw_prompt,
        scores=result.scores,
        overall=result.overall,
        strengths=result.strengths,
        weaknesses=result.weaknesses,
        rewrite_suggestion=result.rewrite_suggestion,
    )


@app.post("/compare", response_model=CompareResponse, tags=["scoring"])
def compare(req: CompareRequest):
    if req.mock:
        os.environ["PROMPTSCOPE_MOCK"] = "1"
    else:
        os.environ["PROMPTSCOPE_MOCK"] = "0"

    import importlib
    import promptscope.scorer as sc
    importlib.reload(sc)

    if not req.prompt_a.strip() or not req.prompt_b.strip():
        raise HTTPException(status_code=422, detail="both prompts required")

    result = sc.compare_prompts(req.prompt_a, req.prompt_b)

    return CompareResponse(
        winner=result.get("winner", "tie"),
        reasoning=result.get("reasoning", ""),
        a_advantages=result.get("a_advantages", []),
        b_advantages=result.get("b_advantages", []),
    )


@app.get("/history", tags=["history"])
def history(limit: int = 10):
    return get_history(limit)


@app.get("/history/{record_id}", tags=["history"])
def history_detail(record_id: int):
    rec = get_by_id(record_id)
    if not rec:
        raise HTTPException(status_code=404, detail=f"Record {record_id} not found")
    return rec


@app.delete("/history/{record_id}", tags=["history"])
def history_delete(record_id: int):
    deleted = delete_record(record_id)
    if not deleted:
        raise HTTPException(status_code=404, detail=f"Record {record_id} not found")
    return {"deleted": record_id}


@app.get("/health", tags=["meta"])
def health():
    return {"status": "ok"}


class BatchRequest(BaseModel):
    prompts: list[str]
    mock: bool = False
    save: bool = True


@app.post("/batch", tags=["scoring"])
def batch(req: BatchRequest):
    if not req.prompts:
        raise HTTPException(status_code=422, detail="prompts list cannot be empty")

    if req.mock:
        os.environ["PROMPTSCOPE_MOCK"] = "1"
    else:
        os.environ["PROMPTSCOPE_MOCK"] = "0"

    import importlib
    import promptscope.scorer as sc
    importlib.reload(sc)

    results = []
    for p in req.prompts:
        if not p.strip():
            continue
        r = sc.score_prompt(p)
        rid = None
        if req.save:
            rid = save_result(r)
        results.append({
            "id": rid,
            "prompt": r.raw_prompt,
            "scores": r.scores,
            "overall": r.overall,
            "strengths": r.strengths,
            "weaknesses": r.weaknesses,
            "rewrite_suggestion": r.rewrite_suggestion,
        })

    if not results:
        raise HTTPException(status_code=422, detail="no valid prompts provided")

    best = max(results, key=lambda x: x["overall"])
    worst = min(results, key=lambda x: x["overall"])
    avg = round(sum(x["overall"] for x in results) / len(results), 1)

    return {
        "count": len(results),
        "average": avg,
        "best": best["prompt"][:80],
        "worst": worst["prompt"][:80],
        "results": results,
    }
