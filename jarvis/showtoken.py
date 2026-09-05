# -*- coding: utf-8 -*-
"""Print the access token the server will actually accept.

The launchers used to read the token straight from config, while uvicorn was
started with --env-file — so a JARVIS_TOKEN in .env silently won over the
printed one and the token on screen was rejected. This loads the same .env
first, in the same order uvicorn does, so the two can never disagree.

    python -m jarvis.showtoken [path/to/.env]
"""
import os
import sys
from pathlib import Path

PLACEHOLDER = "choose-a-long-secret"


def load_env(path: Path) -> None:
    """Apply a .env the way uvicorn --env-file does: file wins over the environment."""
    if not path.is_file():
        return
    try:
        from dotenv import load_dotenv          # ships with uvicorn[standard]
        load_dotenv(path, override=True)
        return
    except Exception:
        pass
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        val = val.strip().strip('"').strip("'")
        os.environ[key.strip()] = val


def main() -> int:
    root = Path(__file__).resolve().parent.parent
    load_env(Path(sys.argv[1]) if len(sys.argv) > 1 else root / ".env")

    from jarvis.config import operator_token   # imported after .env, it reads JARVIS_DATA
    tok = operator_token()
    if tok == PLACEHOLDER:
        print("JARVIS_TOKEN in .env is still the example placeholder — anyone who "
              "reaches your address can guess it. Delete that line and restart.",
              file=sys.stderr)
    print(tok)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
