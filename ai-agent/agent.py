#!/usr/bin/env python3
"""AI agent: analyses a failed CI log and emails a diagnosis + proposed action.

Commands:
  analyse --log test.log --output proposal.json   diagnose + email alert
  notify  --subject "..." --body "..."            send a plain email

The agent can only *propose* one action from ALLOWED_ACTIONS. It never
generates shell commands; recovery/recovery.py maps actions to fixed code.
"""
import argparse
import json
import os
import smtplib
import sys
from email.message import EmailMessage

import requests

ALLOWED_ACTIONS = {
    "restore_known_good_config": "Restore pytest.ini from recovery/known-good/ and re-run tests.",
    "restart_test_container": "Rebuild and restart the test container, then run a health check.",
    "escalate_to_human": "No safe automatic fix; a human must investigate.",
}
MAX_LOG_CHARS = 6000

SYSTEM_PROMPT = (
    "You are a CI/CD reliability assistant. Analyse the failed pipeline log. "
    "Reply with ONLY a JSON object with keys: "
    '"diagnosis" (short string), "confidence" (0-1 number), '
    f'"action" (one of {sorted(ALLOWED_ACTIONS)}). '
    "Choose restore_known_good_config only if the failure looks like a broken test "
    "configuration (pytest.ini, collection or config errors). Choose "
    "restart_test_container only for container/connection/environment problems. "
    "For real code or test-assertion failures choose escalate_to_human."
)


def read_log(path: str) -> str:
    with open(path, "r", errors="replace") as f:
        text = f.read()
    return text[-MAX_LOG_CHARS:]


def heuristic(log: str) -> dict:
    low = log.lower()
    if any(k in low for k in ("pytest.ini", "error collecting", "usage: pytest", "no tests ran", "unrecognized arguments")):
        action, why = "restore_known_good_config", "Looks like a broken test configuration."
    elif any(k in low for k in ("connection refused", "container", "econnreset", "health")):
        action, why = "restart_test_container", "Looks like a container/environment problem."
    else:
        action, why = "escalate_to_human", "Looks like a genuine code or test failure."
    return {"diagnosis": why + " (heuristic fallback, Foundry not configured)", "confidence": 0.4, "action": action}


def ask_foundry(log: str) -> dict:
    endpoint = os.environ["FOUNDRY_ENDPOINT"].rstrip("/")
    deployment = os.environ["FOUNDRY_DEPLOYMENT"]
    api_version = os.environ.get("FOUNDRY_API_VERSION", "2024-10-21")
    url = f"{endpoint}/openai/deployments/{deployment}/chat/completions?api-version={api_version}"
    resp = requests.post(
        url,
        headers={"api-key": os.environ["FOUNDRY_API_KEY"], "Content-Type": "application/json"},
        json={
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": f"Failed pipeline log (tail):\n{log}"},
            ],
            "temperature": 0,
            "max_tokens": 400,
        },
        timeout=60,
    )
    resp.raise_for_status()
    content = resp.json()["choices"][0]["message"]["content"].strip()
    content = content.removeprefix("```json").removeprefix("```").removesuffix("```").strip()
    return json.loads(content)


def analyse(log: str) -> dict:
    if all(os.environ.get(k) for k in ("FOUNDRY_ENDPOINT", "FOUNDRY_API_KEY", "FOUNDRY_DEPLOYMENT")):
        try:
            result = ask_foundry(log)
        except Exception as exc:  # network, auth, bad JSON...
            print(f"Foundry call failed: {exc}", file=sys.stderr)
            result = heuristic(log)
            result["diagnosis"] += f" Foundry error: {type(exc).__name__}."
    else:
        result = heuristic(log)

    # Guardrail: never trust the model beyond the allow-list.
    if result.get("action") not in ALLOWED_ACTIONS:
        result["action"] = "escalate_to_human"
        result["diagnosis"] = str(result.get("diagnosis", "")) + " (invalid action replaced by escalation)"
    result.setdefault("diagnosis", "No diagnosis")
    result.setdefault("confidence", 0)
    return result


def send_email(subject: str, body: str) -> bool:
    needed = ("SMTP_HOST", "SMTP_USER", "SMTP_PASSWORD", "ALERT_EMAIL_TO")
    if not all(os.environ.get(k) for k in needed):
        print("SMTP not configured; printing email instead.\n---\n" + subject + "\n" + body)
        return False
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = os.environ["SMTP_USER"]
    msg["To"] = os.environ["ALERT_EMAIL_TO"]
    msg.set_content(body)
    with smtplib.SMTP(os.environ["SMTP_HOST"], int(os.environ.get("SMTP_PORT", "587")), timeout=30) as s:
        s.starttls()
        s.login(os.environ["SMTP_USER"], os.environ["SMTP_PASSWORD"])
        s.send_message(msg)
    return True


def cmd_analyse(args) -> None:
    log = read_log(args.log)
    proposal = analyse(log)
    run_url = os.environ.get("RUN_URL", "(local run)")
    proposal["failed_run_url"] = run_url
    with open(args.output, "w") as f:
        json.dump(proposal, f, indent=2)

    repo_actions = os.environ.get("ACTIONS_URL", "")
    body = (
        f"Pipeline failure detected.\n\nFailed run: {run_url}\n\n"
        f"Diagnosis: {proposal['diagnosis']}\nConfidence: {proposal['confidence']}\n"
        f"Proposed action: {proposal['action']} - {ALLOWED_ACTIONS[proposal['action']]}\n\n"
    )
    if proposal["action"] == "escalate_to_human":
        body += "No automatic recovery will be started.\n"
    else:
        body += f"A recovery run is waiting for your approval. Review and approve it here:\n{repo_actions}\n"
    body += f"\n--- Log tail ---\n{log[-1500:]}"
    send_email(f"[CI FAILED] Proposed action: {proposal['action']}", body)
    print(json.dumps(proposal, indent=2))


def cmd_notify(args) -> None:
    send_email(args.subject, args.body)


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("analyse")
    a.add_argument("--log", required=True)
    a.add_argument("--output", default="proposal.json")
    a.set_defaults(fn=cmd_analyse)
    n = sub.add_parser("notify")
    n.add_argument("--subject", required=True)
    n.add_argument("--body", required=True)
    n.set_defaults(fn=cmd_notify)
    args = p.parse_args()
    args.fn(args)


if __name__ == "__main__":
    main()
