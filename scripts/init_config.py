"""Create config.json with a random local token (safe to re-run)."""

from __future__ import annotations

import json
import secrets
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def main() -> int:
    cfg_path = ROOT / "config.json"
    example = ROOT / "config.example.json"
    if not example.is_file():
        print("config.example.json missing", file=sys.stderr)
        return 1
    if cfg_path.is_file():
        data = json.loads(cfg_path.read_text(encoding="utf-8-sig"))
        token = data.get("token") or ""
        if not token or token == "REPLACE_ME":
            token = secrets.token_hex(16)
            data["token"] = token
            cfg_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"config.json already exists (token unchanged): {token}")
        return 0
    data = json.loads(example.read_text(encoding="utf-8-sig"))
    token = secrets.token_hex(16)
    data["token"] = token
    cfg_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    print("config.json created")
    print(f"token: {token}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
