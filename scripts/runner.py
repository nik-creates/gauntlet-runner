import hashlib
import hmac
import json
import os
import re
import subprocess
import sys
import tarfile
import time
import urllib.error
import urllib.request
from pathlib import Path

JOB_ID_RE = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")
ROOT = Path(__file__).resolve().parent.parent


def work_dir() -> Path:
    return Path(os.environ.get("RUNNER_TEMP", "/tmp")) / "work"


def sign(key: bytes, action: str, job_id: str, body: bytes) -> str:
    return hmac.new(key, f"{action}.{job_id}.".encode() + body, hashlib.sha256).hexdigest()


def post(action: str, job_id: str, payload: dict) -> dict:
    body = json.dumps(payload, separators=(",", ":")).encode()
    req = urllib.request.Request(
        f"{os.environ['GATEWAY_URL'].rstrip('/')}/runner/jobs/{job_id}/{action}",
        data=body,
        method="POST",
        headers={
            "Content-Type": "application/json",
            "X-Runner-Signature": sign(os.environ["RUNNER_KEY"].encode(), action, job_id, body),
        },
    )
    for attempt in range(4):
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                return json.load(r)
        except urllib.error.HTTPError as e:
            if e.code < 500:
                raise
        except urllib.error.URLError:
            pass
        time.sleep(2 ** attempt * 3)
    raise RuntimeError("gateway unreachable")


def allowed_images() -> set[str]:
    lines = (ROOT / "images.txt").read_text().splitlines()
    return {l.strip() for l in lines if l.strip() and not l.startswith("#")}


def verdict_from(result: dict | None, total: int, timed_out: bool) -> dict:
    failed = {"status": "completed", "verdict": "failed", "tests_passed": 0, "tests_total": total}
    if result is None or timed_out:
        return failed
    passed, got_total = result.get("passed"), result.get("total")
    valid = (
        type(passed) is int and type(got_total) is int
        and got_total == total and 0 <= passed <= got_total
    )
    if not valid:
        return failed
    return {
        "status": "completed",
        "verdict": "passed" if passed == got_total else "failed",
        "tests_passed": passed,
        "tests_total": got_total,
    }


def fetch(url: str, dest: Path) -> None:
    with urllib.request.urlopen(url, timeout=120) as r, open(dest, "wb") as f:
        while chunk := r.read(1 << 20):
            f.write(chunk)


def extract(archive: Path, dest: Path) -> None:
    dest.mkdir(parents=True, exist_ok=True)
    with tarfile.open(archive) as t:
        t.extractall(dest, filter="data")


def cmd_claim(job_id: str) -> None:
    w = work_dir()
    w.mkdir(parents=True, exist_ok=True)
    urls = post("claim", job_id, {"run_id": os.environ.get("GITHUB_RUN_ID")})
    fetch(urls["bundle_url"], w / "bundle.tar.gz")
    fetch(urls["tests_url"], w / "tests.tar.gz")
    extract(w / "bundle.tar.gz", w / "repo")
    extract(w / "tests.tar.gz", w / "tests")
    if urls.get("patch_url"):
        fetch(urls["patch_url"], w / "patch.diff")
        subprocess.run(["git", "apply", "--whitespace=nowarn", str(w / "patch.diff")], cwd=w / "repo", check=True)
    manifest = json.loads((w / "tests" / "manifest.json").read_text())
    if manifest["image"] not in allowed_images():
        raise SystemExit("image not allowed")
    (w / "out").mkdir(exist_ok=True)
    for d in ("repo", "out"):
        subprocess.run(["chmod", "-R", "a+rwX", str(w / d)], check=True)
    for name in ("bundle.tar.gz", "tests.tar.gz", "patch.diff"):
        (w / name).unlink(missing_ok=True)
    with open(os.environ["GITHUB_OUTPUT"], "a") as f:
        f.write(f"image={manifest['image']}\ntimeout={int(manifest.get('timeout', 120))}\n")


def cmd_report(job_id: str) -> None:
    w = work_dir()
    manifest_path = w / "tests" / "manifest.json"
    infra_ok = (
        os.environ.get("CLAIM_OUTCOME") == "success"
        and os.environ.get("PULL_OUTCOME") == "success"
        and manifest_path.exists()
    )
    if not infra_ok:
        post("result", job_id, {"status": "error"})
        return
    total = int(json.loads(manifest_path.read_text())["tests_total"])
    exit_file = w / "exit_code"
    timed_out = exit_file.exists() and exit_file.read_text().strip() in ("124", "137")
    result = None
    try:
        result = json.loads((w / "out" / "result.json").read_text())
    except (OSError, ValueError):
        pass
    payload = verdict_from(result if isinstance(result, dict) else None, total, timed_out)
    post("result", job_id, payload)
    print(f"{payload['verdict']} {payload['tests_passed']}/{payload['tests_total']}")


def main() -> None:
    cmd, job_id = sys.argv[1], os.environ.get("JOB_ID", "")
    if not JOB_ID_RE.match(job_id):
        raise SystemExit("bad job id")
    {"claim": cmd_claim, "report": cmd_report}[cmd](job_id)


if __name__ == "__main__":
    main()
