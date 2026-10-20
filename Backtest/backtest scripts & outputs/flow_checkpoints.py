"""Opt-in, parameter-keyed checkpoints for completed read-only flow requests."""

from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import tempfile
from research_api import ResearchAPIError


def flow_page(base_url, params, fetch, checkpoint_dir=None):
    key = {"source": base_url, "params": params}
    path = None
    if checkpoint_dir is not None:
        root = Path(checkpoint_dir)
        root.mkdir(parents=True, exist_ok=True, mode=0o700)
        digest = hashlib.sha256(json.dumps(key, sort_keys=True).encode()).hexdigest()
        path = root / f"flow-{digest}.json"
        if path.exists():
            saved = json.loads(path.read_text(encoding="utf-8"))
            if saved.get("schema") != "flow-page-v1" or saved.get("request") != key or not isinstance(saved.get("rows"), list):
                raise ValueError("Invalid flow checkpoint; use a separate directory for a fresh run")
            return saved["rows"], "checkpoint"
    raw = fetch("/api/main-flow", params)
    if raw is None:
        raise ResearchAPIError("Flow page request failed; stop rather than interpreting it as zero flow")
    if isinstance(raw, list):
        rows = raw
    elif isinstance(raw, dict) and any(isinstance(raw.get(k), list) for k in ("bars", "data")):
        rows = next(raw[k] for k in ("bars", "data") if isinstance(raw.get(k), list))
    else:
        raise ValueError("Unexpected main-flow response; cannot infer an empty dataset")
    if path is not None:
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent,
                                              prefix=".flow-", delete=False) as output:
                temporary = Path(output.name)
                json.dump({"schema": "flow-page-v1", "request": key,
                           "fetched_at": datetime.now(timezone.utc).isoformat(), "rows": rows},
                          output, allow_nan=False)
            os.replace(temporary, path)
        finally:
            if temporary is not None and temporary.exists():
                temporary.unlink()
    return rows, "api"
