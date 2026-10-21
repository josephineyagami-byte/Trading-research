"""Switch the web service to a checked alternate build, retaining a rollback receipt."""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import shutil
import subprocess
import time
from urllib.request import urlopen


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", required=True)
    parser.add_argument("--dist-dir", required=True)
    parser.add_argument("--previous-dist-dir")
    args = parser.parse_args()
    root = Path(args.root).resolve()
    dist = args.dist_dir
    if dist != ".next" and (not dist.startswith(".next-flow-") or Path(dist).name != dist):
        parser.error("Expected a named alternate flow build")
    build = root/"web"/dist
    if not (build/"BUILD_ID").is_file() or not (build/"server/app/(app)/(research)/flow-model/page.js").is_file():
        raise ValueError("The flow page production build is incomplete")
    snapshots = root/".runtime-config/flow-model"
    if not (snapshots/"MSFT.json").is_file():
        raise ValueError("No checked model snapshot")
    # Preserve hashed chunks for already-open pages during the web-only restart.
    for old_dist in (".next", args.previous_dist_dir):
        if not old_dist:
            continue
        if old_dist != ".next" and (not old_dist.startswith(".next-flow-") or Path(old_dist).name != old_dist):
            parser.error("Invalid previous build")
        old_static = root/"web"/old_dist/"static"
        for source in old_static.rglob("*"):
            target = build/"static"/source.relative_to(old_static)
            if source.is_file() and not source.is_symlink() and not target.exists():
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, target)
    dropin = Path("/etc/systemd/system/us-stock-web.service.d/flow-model.conf")
    def config(name):
        build_setting = '' if name == ".next" else 'Environment="NEXT_DIST_DIR='+name+'"\n'
        return '[Service]\n'+build_setting+'Environment="FLOW_MODEL_SNAPSHOT_DIR='+str(snapshots)+'"\n'
    previous = dropin.read_text() if dropin.exists() else None
    if previous is not None and (not args.previous_dist_dir or previous != config(args.previous_dist_dir)):
        raise ValueError("The existing override differs from the explicitly selected previous build")
    receipt = root/".runtime-config"/("flow-activation-"+datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")+".json")
    dropin.parent.mkdir(parents=True, exist_ok=True)
    dropin.write_text(config(dist))
    receipt.write_text(json.dumps({"distDir": dist, "override": str(dropin), "previousOverride": previous, "status": "switching"}, indent=2))
    try:
        subprocess.run(["systemctl", "daemon-reload"], check=True)
        subprocess.run(["systemctl", "restart", "us-stock-web.service"], check=True)
        for attempt in range(20):
            try:
                with urlopen("http://127.0.0.1:3000/login", timeout=3) as response:
                    if response.status == 200:
                        break
            except OSError:
                if attempt == 19:
                    raise
                time.sleep(1)
        receipt.write_text(json.dumps({"distDir": dist, "override": str(dropin), "previousOverride": previous, "status": "active"}, indent=2))
    except Exception:
        if previous is None:
            dropin.unlink()
        else:
            dropin.write_text(previous)
        subprocess.run(["systemctl", "daemon-reload"], check=True)
        subprocess.run(["systemctl", "restart", "us-stock-web.service"], check=True)
        receipt.write_text(json.dumps({"distDir": dist, "status": "rolled_back"}, indent=2))
        raise
    print(json.dumps({"status": "active", "receipt": str(receipt), "distDir": dist}))


if __name__ == "__main__":
    main()
