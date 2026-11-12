"""Block API keys, passwords and private data from being committed or pushed.

    python tools/check_secrets.py --staged          # pre-commit: files about to be committed
    python tools/check_secrets.py --push            # pre-push: commits about to be pushed (reads stdin)
    python tools/check_secrets.py --all             # CI: every tracked file + full git history

Exit code 1 = something was found (the commit/push is stopped).
If a line is a deliberate false alarm, add the comment  secret-scan: allow  to it.
"""
import argparse
import re
import subprocess
import sys

PATTERNS = [
    ("Anthropic API key", re.compile(r"sk-ant-[A-Za-z0-9_\-]{20,}")),
    ("OpenAI API key", re.compile(r"\bsk-(?:proj-)?[A-Za-z0-9]{20,}")),
    ("Google API key", re.compile(r"\bAIza[0-9A-Za-z_\-]{35}\b")),
    ("AWS access key", re.compile(r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b")),
    ("AWS secret key", re.compile(r"(?i)aws_secret_access_key\s*[=:]\s*['\"]?[A-Za-z0-9/+=]{40}")),
    ("GitHub token", re.compile(r"\bgh[pousr]_[A-Za-z0-9]{36,}\b")),
    ("Private key", re.compile(r"-----BEGIN (?:RSA |EC |DSA |OPENSSH |PGP )?PRIVATE KEY")),
    ("Hard-coded secret", re.compile(
        r"(?i)\b(?:api[_-]?key|secret|password|passwd|access[_-]?token|client[_-]?secret)\b\s*[=:]\s*"
        r"['\"][^'\"\s]{12,}['\"]")),
]
ALLOW_MARK = "secret-scan: allow"

# Files that should never be in the repo (your database, keys, receipts).
BLOCKED_FILES = [
    (re.compile(r"(^|/)\.env(\.[^/]*)?$"), ".env file"),
    (re.compile(r"\.(db|sqlite|sqlite3|db-wal|db-shm)$", re.I), "database file"),
    (re.compile(r"\.(pem|key|p12|pfx)$", re.I), "key/certificate file"),
    (re.compile(r"(^|/)data/"), "app data folder"),
    (re.compile(r"(^|/)receipts/.*\.(jpe?g|png|pdf|webp)$", re.I), "receipt image"),
]
SAFE_FILES = re.compile(r"(^|/)\.env\.example$")
ZERO_SHA = "0" * 40


def git(*args, check=True) -> str:
    r = subprocess.run(["git", *args], capture_output=True, text=True, encoding="utf-8", errors="replace")
    if check and r.returncode != 0:
        sys.exit(f"secret check: git {' '.join(args)} failed: {r.stderr.strip()}")
    return r.stdout


def scan_text(label: str, text: str, findings: list) -> None:
    for n, line in enumerate(text.splitlines(), 1):
        if ALLOW_MARK in line:
            continue
        for name, rx in PATTERNS:
            if rx.search(line):
                findings.append(f"{label}:{n}: {name}")


def check_path(path: str, findings: list) -> None:
    p = path.replace("\\", "/")
    if SAFE_FILES.search(p):
        return
    for rx, what in BLOCKED_FILES:
        if rx.search(p):
            findings.append(f"{p}: {what} must not be committed")
            return


def scan_staged(findings: list) -> None:
    for path in git("diff", "--cached", "--name-only", "--diff-filter=ACMR", "-z").split("\0"):
        if not path:
            continue
        check_path(path, findings)
        blob = subprocess.run(["git", "show", f":{path}"], capture_output=True).stdout
        if b"\0" in blob[:8000]:
            continue  # binary
        scan_text(path, blob.decode("utf-8", "replace"), findings)


def scan_patch(patch: str, findings: list) -> None:
    """Scan added lines and file names in `git log -p` output."""
    current, commit = "?", "?"
    for line in patch.splitlines():
        if line.startswith("commit "):
            commit = line.split()[1][:8]
        elif line.startswith("+++ b/"):
            current = line[6:]
            check_path(current, findings)
        elif line.startswith("+") and not line.startswith("+++"):
            if ALLOW_MARK in line:
                continue
            for name, rx in PATTERNS:
                if rx.search(line):
                    findings.append(f"{current} (commit {commit}): {name}")


def scan_push(findings: list) -> None:
    # git passes: <local ref> <local sha> <remote ref> <remote sha>, one line per ref
    for line in sys.stdin.read().splitlines():
        parts = line.split()
        if len(parts) != 4:
            continue
        _, local_sha, _, remote_sha = parts
        if local_sha == ZERO_SHA:
            continue  # deleting a branch
        if remote_sha == ZERO_SHA:
            rng = [local_sha, "--not", "--remotes"]  # new branch: everything not on the remote yet
        else:
            rng = [f"{remote_sha}..{local_sha}"]
        scan_patch(git("log", "-p", "--no-color", "--format=commit %H", *rng), findings)


def scan_all(findings: list) -> None:
    for path in git("ls-files", "-z").split("\0"):
        if not path:
            continue
        check_path(path, findings)
        try:
            with open(path, "rb") as f:
                data = f.read()
        except OSError:
            continue
        if b"\0" not in data[:8000]:
            scan_text(path, data.decode("utf-8", "replace"), findings)
    # Also scan history: a key removed in a later commit is still public on GitHub.
    scan_patch(git("log", "-p", "--all", "--no-color", "--format=commit %H", check=False), findings)


def main() -> int:
    ap = argparse.ArgumentParser()
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--staged", action="store_true")
    g.add_argument("--push", action="store_true")
    g.add_argument("--all", action="store_true")
    args = ap.parse_args()

    findings: list = []
    if args.staged:
        scan_staged(findings)
    elif args.push:
        scan_push(findings)
    else:
        scan_all(findings)

    findings = sorted(set(findings))
    if not findings:
        print("secret check: OK")
        return 0
    print("\nSECRET CHECK FAILED - this was blocked because it looks like it contains private data:\n")
    for f in findings:
        print("  - " + f)
    print("\nRemove it (keep keys in KaupBudget's Settings, never in code), then try again.")
    print(f"If it's a false alarm, add the comment '{ALLOW_MARK}' to that line.\n")
    return 1


if __name__ == "__main__":
    sys.exit(main())
