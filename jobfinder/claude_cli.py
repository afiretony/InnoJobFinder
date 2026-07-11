import json
import logging
import os
import subprocess

log = logging.getLogger("jobfinder.claude")

CLAUDE_BIN = "claude"


class RateLimitError(RuntimeError):
    """Claude subscription session limit hit (429) — retry after the window resets."""


def _raise_for_output(text: str, context: str):
    if '"api_error_status":429' in text or "hit your session limit" in text:
        raise RateLimitError(f"claude session limit hit: {context[:300]}")


def run_claude(
    prompt: str,
    model: str = "",
    cwd: str | None = None,
    allowed_tools: str | None = None,
    timeout: int = 300,
    thinking_tokens: int = 0,
) -> str:
    """Run claude -p headlessly and return the result text."""
    cmd = [CLAUDE_BIN, "-p", "--output-format", "json"]
    if model:
        cmd += ["--model", model]
    if allowed_tools is not None:
        cmd += ["--allowedTools", allowed_tools]
    env = os.environ.copy()
    if thinking_tokens:
        env["MAX_THINKING_TOKENS"] = str(thinking_tokens)
    proc = subprocess.run(
        cmd,
        input=prompt,
        capture_output=True,
        text=True,
        cwd=cwd,
        env=env,
        timeout=timeout,
    )
    if proc.returncode != 0:
        detail = proc.stderr.strip()[:500] or proc.stdout.strip()[:500]
        _raise_for_output(proc.stdout + proc.stderr, detail)
        raise RuntimeError(f"claude exited {proc.returncode}: {detail}")
    payload = json.loads(proc.stdout)
    if payload.get("is_error"):
        _raise_for_output(proc.stdout, str(payload.get("result")))
        raise RuntimeError(f"claude error result: {str(payload.get('result'))[:500]}")
    return payload.get("result", "")


def extract_json(text: str):
    """Parse JSON out of a model response, tolerating code fences and prose."""
    text = text.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    # strip fences
    if "```" in text:
        for chunk in text.split("```"):
            chunk = chunk.strip()
            if chunk.startswith("json"):
                chunk = chunk[4:].strip()
            if chunk.startswith("[") or chunk.startswith("{"):
                try:
                    return json.loads(chunk)
                except json.JSONDecodeError:
                    continue
    # first bracket to last bracket
    for open_c, close_c in (("[", "]"), ("{", "}")):
        i, j = text.find(open_c), text.rfind(close_c)
        if i != -1 and j > i:
            try:
                return json.loads(text[i : j + 1])
            except json.JSONDecodeError:
                continue
    raise ValueError(f"no JSON found in response: {text[:300]}")
