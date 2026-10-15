"""
Minimal language-model client with tool use, for two providers. Standard library only.

  Anthropic  set ANTHROPIC_API_KEY   (Claude)
  Groq       set GROQ_API_KEY        (open models such as Llama, OpenAI-compatible API)

config/agents.yaml > synapse > provider: "auto" picks whichever key is set (Anthropic first),
or force "anthropic" / "groq". available() is False with no key: callers use templates.
"""
import json
import os
import re
import urllib.request

from ..core import config

ANTHROPIC_API = "https://api.anthropic.com/v1/messages"
GROQ_API = "https://api.groq.com/openai/v1/chat/completions"


def provider():
    wanted = config.agents()["synapse"].get("provider", "auto")
    has = {"anthropic": bool(os.environ.get("ANTHROPIC_API_KEY")), "groq": bool(os.environ.get("GROQ_API_KEY"))}
    if wanted in has:
        return wanted if has[wanted] else None
    return "anthropic" if has["anthropic"] else "groq" if has["groq"] else None


def available():
    return provider() is not None


def model_for(role):
    """role: explainer | copilot | alert. Model names come from config/agents.yaml."""
    c = config.agents()["synapse"]
    return c[f"groq_{role}_model"] if provider() == "groq" else c[f"{role}_model"]


def _post(url, body, headers):
    req = urllib.request.Request(url, data=json.dumps(body).encode(),
                                 headers={"content-type": "application/json", **headers})
    with urllib.request.urlopen(req, timeout=90) as r:
        return json.load(r)


def chat(model, system, user, tools=None, handlers=None, max_tokens=1200, max_rounds=5):
    """One conversation. If tools are given, the model may call them (handlers: name -> function
    returning a JSON-serialisable result) for up to max_rounds before answering.
    Returns (final text, list of tool calls made). `model` may be a role name or a model id."""
    if model in ("explainer", "copilot", "alert"):
        model = model_for(model)
    if provider() == "groq":
        return _chat_groq(model, system, user, tools, handlers, max_tokens, max_rounds)
    return _chat_anthropic(model, system, user, tools, handlers, max_tokens, max_rounds)


def _run_tool(handlers, name, args):
    fn = (handlers or {}).get(name)
    try:
        out = fn(**(args or {})) if fn else {"error": "unknown tool"}
    except Exception as e:                      # a tool error is reported to the model, not raised
        out = {"error": str(e)}
    return json.dumps(out, ensure_ascii=False, default=str)[:12000]


def _chat_anthropic(model, system, user, tools, handlers, max_tokens, max_rounds):
    headers = {"anthropic-version": "2023-06-01", "x-api-key": os.environ["ANTHROPIC_API_KEY"]}
    messages, calls = [{"role": "user", "content": user}], []
    for _ in range(max_rounds):
        body = {"model": model, "max_tokens": max_tokens, "system": system, "messages": messages}
        if tools:
            body["tools"] = tools
        data = _post(ANTHROPIC_API, body, headers)
        content = data.get("content", [])
        if data.get("stop_reason") != "tool_use":
            return "".join(b.get("text", "") for b in content if b.get("type") == "text").strip(), calls
        messages.append({"role": "assistant", "content": content})
        results = []
        for b in content:
            if b.get("type") == "tool_use":
                calls.append({"tool": b["name"], "input": b.get("input")})
                results.append({"type": "tool_result", "tool_use_id": b["id"],
                                "content": _run_tool(handlers, b["name"], b.get("input"))})
        messages.append({"role": "user", "content": results})
    return "", calls


def _chat_groq(model, system, user, tools, handlers, max_tokens, max_rounds):
    """Groq speaks the OpenAI chat-completions format: tools become 'functions'."""
    headers = {"authorization": f"Bearer {os.environ['GROQ_API_KEY']}"}
    messages = [{"role": "system", "content": system}, {"role": "user", "content": user}]
    fns = [{"type": "function", "function": {"name": t["name"], "description": t["description"],
                                             "parameters": t["input_schema"]}} for t in tools or []]
    calls = []
    for _ in range(max_rounds):
        body = {"model": model, "max_tokens": max_tokens, "messages": messages, "temperature": 0.2}
        if fns:
            body["tools"] = fns
        msg = _post(GROQ_API, body, headers)["choices"][0]["message"]
        tool_calls = msg.get("tool_calls") or []
        if not tool_calls:
            return (msg.get("content") or "").strip(), calls
        messages.append({"role": "assistant", "content": msg.get("content") or "", "tool_calls": tool_calls})
        for tc in tool_calls:
            name = tc["function"]["name"]
            try:
                args = json.loads(tc["function"].get("arguments") or "{}")
            except json.JSONDecodeError:
                args = {}
            calls.append({"tool": name, "input": args})
            messages.append({"role": "tool", "tool_call_id": tc["id"], "content": _run_tool(handlers, name, args)})
    return "", calls


def extract_json(text):
    """First JSON object or array in a model reply (tolerates ```json fences)."""
    text = re.sub(r"```(?:json)?", "", text or "")
    for opener, closer in (("{", "}"), ("[", "]")):
        i, j = text.find(opener), text.rfind(closer)
        if i != -1 and j > i:
            try:
                return json.loads(text[i:j + 1])
            except json.JSONDecodeError:
                continue
    return None
