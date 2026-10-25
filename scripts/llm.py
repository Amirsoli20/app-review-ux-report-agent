"""Run a sub-agent from .claude/agents/<name>.md on a JSON payload and return its JSON answer.

The agent file is the single source of its prompt: its body plus the bodies of the skills named in its
frontmatter (`skills:`) form the system prompt. The same files are used when Claude Code runs the
agents interactively.

Backends
- claude-cli: headless `claude -p`, using the Claude Code login on this machine (default when no API key)
- anthropic:  the Anthropic API (when ANTHROPIC_API_KEY is set and the `anthropic` package is installed)

Every answer is cached in <run>/ai/<agent>/<hash>.json, so a re-run with the same inputs and prompts
reuses it (reproducibility, NFR-3) and an interrupted run resumes where it stopped.
"""
import json
import os
import re
import shutil
import subprocess
import tempfile
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import jsonschema
import yaml

from common import AGENTS, SKILLS, schema, sha

MODEL_TIER = {"haiku": "fast", "sonnet": "strong", "opus": "strong", "fast": "fast", "strong": "strong"}
_lock = threading.Lock()
USAGE = {"calls": 0, "cached": 0, "failed": 0, "cost_usd": 0.0, "by_agent": {}, "models_used": {}, "tokens": {}}
MODEL_FALLBACK = {}


class UsageLimit(SystemExit):
    """The Claude account's usage limit is reached. Degraded output would be worse than stopping, so the
    run stops and can be resumed later with --resume."""
  # configured model id -> CLI alias, when the installed Claude Code rejects the id


def _split_frontmatter(text):
    m = re.match(r"^---\n(.*?)\n---\n(.*)$", text, re.S)
    if not m:
        return {}, text
    return yaml.safe_load(m.group(1)) or {}, m.group(2)


def skill_text(name):
    fm, body = _split_frontmatter((SKILLS / name / "SKILL.md").read_text(encoding="utf-8"))
    return "# Skill: %s\n\n%s" % (name, body.strip())


class Agent:
    def __init__(self, name, settings):
        fm, body = _split_frontmatter((AGENTS / (name + ".md")).read_text(encoding="utf-8"))
        self.name = name
        self.tier = MODEL_TIER.get(str(fm.get("model", "haiku")).lower(), "fast")
        self.model = settings["models"][self.tier]
        skills = fm.get("skills") or []
        if isinstance(skills, str):
            skills = [x.strip() for x in skills.split(",") if x.strip()]
        self.skills = skills
        self.system = "\n\n".join([body.strip()] + [skill_text(s) for s in skills])
        self.version = sha(self.system, 10)
        self.timeout = int((settings.get("ai_timeout_seconds") or {}).get(self.tier, 1800)
                           if isinstance(settings.get("ai_timeout_seconds"), dict) else settings.get("ai_timeout_seconds", 1800))
        self.effort = (settings.get("ai_effort") or {"fast": "low", "strong": "medium"}).get(self.tier)
        self.backend = pick_backend(settings.get("ai_backend", "auto"))


def pick_backend(choice):
    if choice == "anthropic" or (choice == "auto" and os.environ.get("ANTHROPIC_API_KEY")):
        try:
            import anthropic  # noqa: F401
            return "anthropic"
        except ImportError:
            if choice == "anthropic":
                raise
    if not shutil.which("claude"):
        raise SystemExit("No AI backend: install Claude Code (`claude`) or set ANTHROPIC_API_KEY and pip install anthropic")
    return "claude-cli"


def _call_cli(agent, user):
    env = {k: v for k, v in os.environ.items() if not k.startswith("CLAUDECODE") and k != "CLAUDE_CODE_ENTRYPOINT"}
    cwd = Path(tempfile.gettempdir()) / "app-review-ux-ai"  # outside the project, so no CLAUDE.md is loaded
    cwd.mkdir(exist_ok=True)
    for _ in range(2):
        model = MODEL_FALLBACK.get(agent.model, agent.model)
        cmd = ["claude", "-p", "--model", model, "--output-format", "json", "--tools", "",
               "--no-session-persistence", "--setting-sources", "", "--strict-mcp-config",
               "--system-prompt", agent.system] + (["--effort", agent.effort] if agent.effort else [])
        p = subprocess.run(cmd, input=user, capture_output=True, text=True, timeout=agent.timeout, cwd=cwd, env=env)
        if p.returncode != 0 and not p.stdout.strip():
            raise RuntimeError("claude exited %d: %s" % (p.returncode, p.stderr[-500:]))
        out = json.loads(p.stdout)
        msg = str(out.get("result"))
        if out.get("is_error") and "does not support this model" in msg and agent.model not in MODEL_FALLBACK:
            # An older Claude Code cannot run the configured model id: use its own alias for the tier
            # ("opus" / "haiku") and record the model that actually answered.
            with _lock:
                MODEL_FALLBACK[agent.model] = "opus" if agent.tier == "strong" else "haiku"
            continue
        break
    if out.get("is_error"):
        if re.search(r"hit your (session|usage|weekly) limit|usage limit|rate limit reached", msg, re.I):
            raise UsageLimit(msg[:300])
        raise RuntimeError("claude error: %s" % msg[:500])
    u = out.get("usage") or {}
    with _lock:
        for m in (out.get("modelUsage") or {}):
            USAGE["models_used"][m] = USAGE["models_used"].get(m, 0) + 1
        t = USAGE["tokens"].setdefault(agent.name, {"input": 0, "cache_read": 0, "cache_write": 0, "output": 0})
        t["input"] += int(u.get("input_tokens") or 0)
        t["cache_read"] += int(u.get("cache_read_input_tokens") or 0)
        t["cache_write"] += int(u.get("cache_creation_input_tokens") or 0)
        t["output"] += int(u.get("output_tokens") or 0)
    return out.get("result") or "", float(out.get("total_cost_usd") or 0)


def _call_api(agent, user):
    import anthropic
    client = anthropic.Anthropic()
    max_tokens = 32000 if agent.tier == "strong" else 16000
    with client.messages.stream(model=agent.model, max_tokens=max_tokens, temperature=0, system=agent.system,
                                messages=[{"role": "user", "content": user}]) as s:
        msg = s.get_final_message()
    text = "".join(b.text for b in msg.content if getattr(b, "type", "") == "text")
    return text, 0.0


def parse_json(text):
    t = text.strip()
    m = re.search(r"```(?:json)?\s*(.*?)```", t, re.S)
    if m:
        t = m.group(1).strip()
    try:
        return json.loads(t)
    except ValueError:
        i, j = t.find("{"), t.rfind("}")
        if i >= 0 and j > i:
            return json.loads(t[i:j + 1])
        raise


def _public(o):
    """Drop keys starting with "_": code-side bookkeeping that the model does not need to see."""
    if isinstance(o, dict):
        return {k: _public(v) for k, v in o.items() if not str(k).startswith("_")}
    if isinstance(o, list):
        return [_public(v) for v in o]
    return o


def _message(payload, feedback=None):
    msg = "Input JSON:\n```json\n%s\n```\n\nReturn only the JSON object described in your instructions, with no other text." % (
        json.dumps(_public(payload), ensure_ascii=False, separators=(",", ":")))
    if feedback:
        msg += "\n\nYour previous answer was rejected:\n%s\nReturn the complete corrected JSON object." % feedback
    return msg


def call(agent, payload, run, schema_name=None, check=None, tag=None, return_last=False):
    """Run the agent once (plus one corrective retry). Returns the parsed JSON, or raises RuntimeError.

    With return_last, an answer that parsed and passed the schema but still failed `check` on the retry is
    returned as is, so the caller can keep its valid records and drop the rest."""
    feedback, last_err, last_obj = None, None, None
    for attempt in (1, 2):
        user = _message(payload, feedback)
        key = sha(agent.model + "\n" + agent.system + "\n" + user, 20)
        cache = run.p("ai", agent.name, key + ".json")
        text, cost, cached = None, 0.0, False
        if cache.exists():
            text, cached = json.load(open(cache, encoding="utf-8"))["response"], True
        else:
            try:
                text, cost = (_call_api if agent.backend == "anthropic" else _call_cli)(agent, user)
            except (RuntimeError, subprocess.TimeoutExpired, ValueError) as e:
                last_err = "call failed: %s" % e
                feedback = None
                continue
        try:
            obj = parse_json(text)
            if schema_name:
                jsonschema.validate(obj, schema(schema_name))
            last_obj = obj
            problems = check(obj) if check else []
            if problems:
                raise ValueError("; ".join(problems[:25]))
        except (ValueError, jsonschema.ValidationError) as e:
            last_err = str(getattr(e, "message", e))[:1500]
            feedback = last_err
            if cached:
                cache.unlink()  # a cached answer that no longer validates is discarded
            continue
        if not cached:
            cache.parent.mkdir(parents=True, exist_ok=True)
            json.dump({"agent": agent.name, "model": agent.model, "prompt_version": agent.version, "tag": tag,
                       "response": text}, open(cache, "w", encoding="utf-8"), ensure_ascii=False)
        with _lock:
            USAGE["calls"] += 0 if cached else 1
            USAGE["cached"] += 1 if cached else 0
            USAGE["cost_usd"] += cost
            a = USAGE["by_agent"].setdefault(agent.name, {"calls": 0, "cached": 0, "retries": 0})
            a["calls" if not cached else "cached"] += 1
            a["retries"] += attempt - 1
        return obj
    if return_last and last_obj is not None:
        with _lock:
            a = USAGE["by_agent"].setdefault(agent.name, {"calls": 0, "cached": 0, "retries": 0})
            a["calls"] += 1
            a["retries"] += 1
        return last_obj
    with _lock:
        USAGE["failed"] += 1
    raise RuntimeError("%s failed twice: %s" % (agent.name, last_err))


def map_batches(agent, payloads, run, schema_name=None, check=None, concurrency=8, label="batch", return_last=False):
    """Run many payloads in parallel. Returns a list of (result or None, error or None), in order."""
    done = [0]

    def one(ix):
        i, p = ix
        try:
            r = call(agent, p, run, schema_name, (lambda o: check(o, p)) if check else None, tag="%s %d" % (label, i),
                     return_last=return_last)
            res = (r, None)
        except RuntimeError as e:
            res = (None, str(e))
        with _lock:
            done[0] += 1
            if done[0] % max(1, len(payloads) // 10) == 0 or done[0] == len(payloads):
                run.log("  %s: %d of %d %ses done" % (agent.name, done[0], len(payloads), label))
        return res

    with ThreadPoolExecutor(max(1, concurrency)) as ex:
        return list(ex.map(one, list(enumerate(payloads))))


def usage_snapshot():
    with _lock:
        return json.loads(json.dumps(USAGE))
