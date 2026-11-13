"""Command-line interface: `secplan serve`, `secplan baseline`, `secplan plan`."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .baseline import assess
from .models import OrgProfile
from .prompts import SYSTEM_PROMPT, build_plan_prompt
from .providers import PROVIDERS, ProviderError, stream_chat


def _load_profile(path: str) -> OrgProfile:
    text = sys.stdin.read() if path == "-" else Path(path).read_text()
    return OrgProfile.model_validate_json(text)


def cmd_serve(args: argparse.Namespace) -> int:
    import uvicorn

    if args.host not in ("127.0.0.1", "localhost"):
        print("Warning: serving beyond localhost. Set SECPLAN_ALLOW_CUSTOM_BASE_URL=0 "
              "and put SecPlan behind authentication.", file=sys.stderr)
    uvicorn.run("secplan.server:app", host=args.host, port=args.port, reload=args.reload)
    return 0


def cmd_baseline(args: argparse.Namespace) -> int:
    print(json.dumps(assess(_load_profile(args.profile)), indent=2))
    return 0


def cmd_plan(args: argparse.Namespace) -> int:
    profile = _load_profile(args.profile)
    prompt = build_plan_prompt(profile, assess(profile))
    out = open(args.output, "w") if args.output else sys.stdout
    try:
        for chunk in stream_chat(args.provider, system=SYSTEM_PROMPT,
                                 messages=[{"role": "user", "content": prompt}],
                                 model=args.model, base_url=args.base_url):
            out.write(chunk)
            out.flush()
        out.write("\n")
    except ProviderError as e:
        print(f"error: {e}", file=sys.stderr)
        return 1
    finally:
        if out is not sys.stdout:
            out.close()
            print(f"Wrote {args.output}", file=sys.stderr)
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="secplan", description="AI-assisted security strategy planner")
    sub = parser.add_subparsers(dest="command", required=True)

    s = sub.add_parser("serve", help="run the web app")
    s.add_argument("--host", default="127.0.0.1")
    s.add_argument("--port", type=int, default=8000)
    s.add_argument("--reload", action="store_true")
    s.set_defaults(func=cmd_serve)

    b = sub.add_parser("baseline", help="score a profile without AI")
    b.add_argument("profile", help="profile JSON file, or - for stdin")
    b.set_defaults(func=cmd_baseline)

    p = sub.add_parser("plan", help="generate an AI strategy (API key from env)")
    p.add_argument("profile", help="profile JSON file, or - for stdin")
    p.add_argument("--provider", default="anthropic", choices=list(PROVIDERS))
    p.add_argument("--model", help="override the provider's default model")
    p.add_argument("--base-url", help="for custom or local OpenAI-compatible servers")
    p.add_argument("-o", "--output", help="write Markdown to this file")
    p.set_defaults(func=cmd_plan)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
