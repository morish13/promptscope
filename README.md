# promptscope

CLI + REST API tool to score, analyze, and improve LLM prompts using Claude.

## Features

- Score any prompt across 5 quality dimensions
- Compare two prompts head-to-head
- Batch score multiple prompts from a file
- View score history and trends over time
- Export history as JSON or CSV
- Full REST API with Swagger UI
- Mock mode for offline use

## Install

```bash
git clone https://github.com/morish13/promptscope
cd promptscope
python3 -m venv venv && source venv/bin/activate
pip install -e .
export ANTHROPIC_API_KEY=your_key_here
```

## CLI Usage

```bash
# score a prompt
promptscope score "Summarize this article in 3 bullet points."

# compare two prompts
promptscope compare "Translate this." "Translate the following text to French. Return JSON."

# batch score from file
promptscope batch prompts.txt

# view history + trend
promptscope history
promptscope trend

# export
promptscope history --export csv --out scores.csv

# offline/mock mode (no API key needed)
promptscope score "any prompt" --mock
```

## API Usage

```bash
uvicorn promptscope.api:app --reload
# docs at http://127.0.0.1:8000/docs
```

```bash
curl -X POST http://127.0.0.1:8000/score \
  -H "Content-Type: application/json" \
  -d '{"prompt": "Summarize this.", "mock": true}'
```

## Score Dimensions

| Dimension | What it measures |
|---|---|
| Clarity | Is the instruction unambiguous? |
| Specificity | Enough context, constraints, format? |
| Goal Alignment | Is the goal achievable from this prompt alone? |
| IFL | Instruction Following Likelihood |
| Ambiguity Risk | Inverse — 10 means no ambiguity |

## Stack

Python 3.10+ · FastAPI · Typer · Rich · SQLite · Claude Sonnet 4
