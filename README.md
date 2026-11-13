# SecPlan

SecPlan is an open-source security strategy planner. You describe your organisation and it scores your security posture straight away, with no AI needed. Then it uses **any AI provider you have a key for** to write a tailored strategy: top risks, a 30/90/365-day roadmap, compliance notes, budget guidance and KPIs. After that you can ask it follow-up questions.

- **Bring your own model:** Anthropic (Claude), OpenAI, Google Gemini, Groq, OpenRouter, Mistral, DeepSeek, Together AI, local models through Ollama or LM Studio, or any OpenAI-compatible endpoint.
- **Baseline without AI:** a rules-based maturity score, NIST CSF 2.0 coverage, prioritised gaps (mapped to CIS Controls v8) and risk drivers. They update live as you fill in the form.
- **Grounded output:** the AI receives your profile *and* the baseline gaps, so the plan targets your real weaknesses instead of giving generic advice.
- **Your keys stay yours:** a key goes only to the provider you choose. It is never written to disk or logged on the server. The browser can optionally remember it in local storage.
- **Web UI and CLI:** export plans as Markdown, or script them from the command line.

## Quick start

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
secplan serve
```

Open http://127.0.0.1:8000, fill in the profile, pick a provider, paste your API key and click **Generate strategy**.

### Setting keys on the server instead

Set the provider's environment variable before running `secplan serve`, then leave the key field blank in the UI.

| Provider | Variable | Default model |
|---|---|---|
| Anthropic | `ANTHROPIC_API_KEY` | `claude-opus-5-5` |
| OpenAI | `OPENAI_API_KEY` | `gpt-5` |
| Google Gemini | `GEMINI_API_KEY` | `gemini-2.5-flash` |
| Groq | `GROQ_API_KEY` | `llama-3.3-70b-versatile` |
| OpenRouter | `OPENROUTER_API_KEY` | `openai/gpt-5` |
| Mistral | `MISTRAL_API_KEY` | `mistral-large-latest` |
| DeepSeek | `DEEPSEEK_API_KEY` | `deepseek-chat` |
| Together AI | `TOGETHER_API_KEY` | `meta-llama/Llama-3.3-70B-Instruct-Turbo` |
| Ollama / LM Studio | none | `llama3.1` / `local-model` |
| Custom (OpenAI-compatible) | `SECPLAN_CUSTOM_API_KEY` | you choose |

Model names change often, and every default can be overridden in the UI or with `--model`.

## CLI

```bash
secplan baseline examples/saas-startup.json
```

```bash
ANTHROPIC_API_KEY=... secplan plan examples/saas-startup.json -o strategy.md
```

```bash
secplan plan examples/saas-startup.json --provider ollama --model llama3.1
```

## API

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/providers` | Supported providers and whether a server-side key is set |
| GET | `/api/controls` | The control catalogue |
| POST | `/api/baseline` | Score a profile (JSON body) |
| POST | `/api/plan` | Stream a strategy as plain text. Body: `{profile, provider, model, base_url, conversation, followup}`; key in the `X-API-Key` header |

Interactive docs are at `/api/docs`.

## Project layout

```
secplan/
  providers.py   provider registry and streaming adapters (Anthropic SDK + OpenAI-compatible)
  baseline.py    control catalogue, maturity scoring, risk drivers
  prompts.py     system prompt and plan structure
  server.py      FastAPI app
  cli.py         command-line interface
  web/           single-page UI (no build step)
tests/           pytest suite (no network calls)
```

## Adding a provider

If the provider speaks the OpenAI Chat Completions protocol, add one `ProviderSpec` entry to `PROVIDERS` in `secplan/providers.py`. Other protocols need a new `_stream_*` adapter.

## Hosting for others

SecPlan is designed to run on your own machine. Before you expose it on a network:

- set `SECPLAN_ALLOW_CUSTOM_BASE_URL=0` so users can't point the server at internal URLs;
- put it behind authentication and HTTPS;
- don't set server-side API keys unless you are happy to pay for everyone's usage.

## Disclaimer

Generated plans are guidance only. They don't replace a qualified security assessment or legal advice on compliance.

## Licence

MIT. See [LICENSE](LICENSE).
