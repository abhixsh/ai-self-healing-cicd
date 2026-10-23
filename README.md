# ai-self-healing-cicd

An AI-powered self-healing CI/CD pipeline using GitHub Actions, Docker, Python, and Microsoft Foundry. Detects pipeline failures, analyses logs, sends email alerts, requests human approval, and performs controlled recovery.

## How it works

1. `ci.yml` runs the tests on every push.
2. On failure, `ai-agent/agent.py` collects the log tail and asks a Microsoft Foundry model for a diagnosis.
3. The model may only choose from an **allow-list** of actions (`restore_known_good_config`, `restart_test_container`, `escalate_to_human`). Anything else is replaced with `escalate_to_human`.
4. You get an email with the error, diagnosis and proposed action.
5. CI dispatches `recovery.yml`, which targets the `recovery-approval` environment and **waits for your approval**.
6. After approval, `recovery/recovery.py` runs the fixed action, tests run again, and you get a result email.

The agent never writes shell commands. `recovery.py` maps each approved action name to fixed code.

## Layout

```
app/                  Flask app + tests
ai-agent/agent.py     Log analysis (Foundry), email alerts
recovery/recovery.py  Allow-listed recovery actions
recovery/known-good/  Known-good pytest.ini used for restore
scripts/health-check.sh
.github/workflows/    ci.yml, recovery.yml
```

## Run locally

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python -m pytest
docker build -t ai-self-healing-cicd:test . && docker run -d -p 5000:5000 ai-self-healing-cicd:test
bash scripts/health-check.sh
```

## Setup on GitHub

1. Create a **public** repo named `ai-self-healing-cicd` and push this project.
2. **Settings > Environments > New environment** named `recovery-approval`; enable **Required reviewers** and add yourself.
3. **Settings > Secrets and variables > Actions**, add:
   - `FOUNDRY_ENDPOINT` (e.g. `https://<resource>.openai.azure.com`)
   - `FOUNDRY_API_KEY`
   - `FOUNDRY_DEPLOYMENT` (your model deployment name)
   - `SMTP_HOST` (e.g. `smtp.gmail.com`), `SMTP_PORT` (`587`), `SMTP_USER`, `SMTP_PASSWORD` (app password), `ALERT_EMAIL_TO`
4. **Settings > Actions > General > Workflow permissions**: allow read/write so CI can dispatch the recovery workflow.

Without Foundry secrets the agent falls back to a simple keyword heuristic; without SMTP secrets it prints the email to the log. So the pipeline works end to end before you finish setup.

## Demo

Break the test config and push:

```bash
echo "addopts = --not-a-real-flag" >> pytest.ini
git commit -am "Break pytest config" && git push
```

CI fails, you get an email proposing `restore_known_good_config`, you approve the recovery run, the config is restored and tests pass.

To demo escalation instead, change `add()` in `app/app.py` to return `a - b`.

## Notes

- Recovery fixes the runner's checkout and verifies the result. It does not push commits. A natural next step is opening a PR with the fix.
- Keep the allow-list small and review any new action before adding it to `ALLOWED_ACTIONS` and `recovery.py`.
