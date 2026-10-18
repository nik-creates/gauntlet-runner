# gauntlet-runner

Public grader for Gauntlet. One workflow (`grade.yml`) run per submission, dispatched by the gateway.

## What it does

1. Claims the job from the gateway (HMAC-signed), downloads the problem bundle, hidden tests and optional patch from short-lived presigned URLs.
2. Runs `tests/run.sh` inside a locked-down container: no network, read-only root, all capabilities dropped, non-root user, CPU/memory/pids caps, hard timeout. Container output is discarded, never logged.
3. Reads `/out/result.json`, validates it against the manifest, and posts a signed verdict to the gateway.

## Required repo secrets

- `GATEWAY_URL`: public URL of the gateway.
- `RUNNER_KEY`: shared signing key, same value as the gateway's `RUNNER_KEY`.

## Tests bundle contract

`tests.tar.gz` must contain `manifest.json` and `run.sh`:

```json
{"image": "python:3.12-slim", "timeout": 120, "tests_total": 5}
```

`run.sh` runs inside the container with the codebase at `/work/repo` and writes `/out/result.json` as `{"passed": N, "total": 5}`. `total` must equal `tests_total` or the run counts as failed. Images must be listed in `images.txt`.

## Security notes

- Everything runs in a single job on purpose: artifacts of public repos are public, so hidden tests can never be handed between jobs.
- Dispatch inputs and logs are public. Inputs carry only the job id, and nothing from the sandbox is printed.
- `RUNNER_KEY` is only set on the claim and report steps, never on the sandbox step.
- Known limit: if user code runs in the same process as the tests, it can write its own `result.json`. Problem authors should have `run.sh` compute the verdict from a process the submitted code cannot influence. Totals are checked against the manifest as a baseline.

## Local tests

```
python3 -m unittest discover -s tests
```
