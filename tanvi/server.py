"""FastAPI app: JSON API plus the static web UI."""

from __future__ import annotations

import os
from itertools import chain
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, Header, HTTPException
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import __version__
from .baseline import assess, catalog_public
from .models import OrgProfile
from .prompts import SYSTEM_PROMPT, build_plan_prompt
from .providers import PROVIDERS, ProviderError, list_models, stream_chat

WEB_DIR = Path(__file__).parent / "web"

app = FastAPI(title="Tanvi", version=__version__, docs_url="/api/docs")


class Turn(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(max_length=200_000)


class PlanRequest(BaseModel):
    profile: OrgProfile
    provider: str = "anthropic"
    model: str = ""
    base_url: str = ""
    # Prior turns after the initial request (the plan, then follow-ups), and the
    # new follow-up question. Empty for a fresh plan.
    conversation: list[Turn] = Field(default_factory=list, max_length=40)
    followup: str = Field("", max_length=4000)


class ModelsRequest(BaseModel):
    provider: str
    base_url: str = ""


def _custom_base_urls_allowed() -> bool:
    # Pointing the server at arbitrary URLs is fine on your own machine, but
    # should be switched off when Tanvi is hosted for other people.
    return os.environ.get("TANVI_ALLOW_CUSTOM_BASE_URL", "1") != "0"


@app.get("/api/health")
def health() -> dict:
    return {"ok": True, "version": __version__}


@app.get("/api/providers")
def providers() -> dict:
    return {
        "providers": [p.to_public() for p in PROVIDERS.values()],
        "custom_base_url_allowed": _custom_base_urls_allowed(),
    }


@app.get("/api/controls")
def controls() -> list[dict]:
    return catalog_public()


@app.post("/api/baseline")
def baseline(profile: OrgProfile) -> dict:
    return assess(profile)


@app.post("/api/models")
def models(req: ModelsRequest, x_api_key: str | None = Header(default=None)) -> dict:
    if req.base_url and not _custom_base_urls_allowed():
        raise HTTPException(400, "Custom base URLs are disabled on this server.")
    try:
        return {"models": list_models(req.provider, api_key=x_api_key,
                                      base_url=req.base_url or None)}
    except ProviderError as e:
        raise HTTPException(400, str(e)) from None


@app.post("/api/plan")
def plan(req: PlanRequest, x_api_key: str | None = Header(default=None)) -> StreamingResponse:
    if req.base_url and not _custom_base_urls_allowed():
        raise HTTPException(400, "Custom base URLs are disabled on this server.")
    if req.conversation and not req.followup.strip():
        raise HTTPException(400, "A follow-up question is required when continuing.")

    messages = [{"role": "user", "content": build_plan_prompt(req.profile, assess(req.profile))}]
    messages += [t.model_dump() for t in req.conversation]
    if req.followup.strip():
        messages.append({"role": "user", "content": req.followup.strip()})

    chunks = stream_chat(
        req.provider, system=SYSTEM_PROMPT, messages=messages,
        model=req.model or None, api_key=x_api_key, base_url=req.base_url or None,
    )
    # Pull the first chunk before responding so bad keys, unknown models and
    # unreachable hosts surface as a clean HTTP error instead of a broken stream.
    try:
        first = next(chunks, "")
    except ProviderError as e:
        raise HTTPException(400, str(e)) from None

    def body():
        try:
            yield from chain([first], chunks)
        except ProviderError as e:
            yield f"\n\n> Error: {e}"

    return StreamingResponse(body(), media_type="text/plain; charset=utf-8",
                             headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"})


@app.get("/", include_in_schema=False)
def index() -> FileResponse:
    return FileResponse(WEB_DIR / "index.html")


app.mount("/static", StaticFiles(directory=WEB_DIR), name="static")
