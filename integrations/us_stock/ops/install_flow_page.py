"""Install only the reviewed flow-page files and small navigation/config additions."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shutil

FILES = ["lib/flow-model.ts", "lib/server/flow-model-store.ts", "app/live-data/flow-model/route.ts",
         "components/research/FlowModelChart.tsx", "app/(app)/(research)/flow-model/page.tsx"]


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--root", required=True)
    p.add_argument("--payload", required=True)
    p.add_argument("--previous-manifest")
    args = p.parse_args()
    web = Path(args.root)/"web"
    tag = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    backup = Path(args.root)/".runtime-config"/("flow-page-backup-"+tag)
    backup.mkdir(parents=True, exist_ok=False)
    manifest = []
    owned = {item["file"]: item["installedSha256"] for item in json.loads(Path(args.previous_manifest).read_text())} if args.previous_manifest else {}

    def save(relative, data):
        path = web/relative
        if path.is_symlink():
            raise ValueError("Refuse symlink destination")
        previous = path.read_bytes() if path.exists() else None
        if previous == data:
            return
        if previous is not None:
            target = backup/relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, target)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        manifest.append({"file": relative, "existed": previous is not None,
                         "installedSha256": hashlib.sha256(data).hexdigest()})
        (backup/"manifest.json").write_text(json.dumps(manifest, indent=2))

    edits = [
      ("components/research/ResearchWorkspace.tsx", '  { href: "/institutions", label: "机构持仓", icon: Building2, aliases: [] },',
       '  { href: "/flow-model", label: "资金流模型", icon: Activity, aliases: [] },', "/flow-model"),
      ("lib/i18n-messages.ts", 'export const messages: ReadonlyArray<readonly [string, string]> = [',
       '  ["资金流模型", "Flow model"],', '"资金流模型"'),
      ("lib/self-authenticated-routes.ts", '  "/live-data/fundamentals",',
       '  "/live-data/flow-model",', '"/live-data/flow-model"'),
      ("next.config.ts", 'const nextConfig: NextConfig = {',
       '  distDir: process.env.NEXT_DIST_DIR || ".next",', "NEXT_DIST_DIR"),
    ]
    changed = {}
    for relative, anchor, addition, marker in edits:
        text = (web/relative).read_text()
        if marker in text:
            continue
        # Older production versions can lack the fundamentals route; use another observed exact route anchor.
        if relative == "lib/self-authenticated-routes.ts" and anchor not in text:
            anchor = '  "/live-data/klines",'
        if text.count(anchor) != 1:
            raise ValueError("Production anchor differs: "+relative)
        changed[relative] = text.replace(anchor, anchor+"\n"+addition, 1).encode()
    for relative in FILES:
        data = (Path(args.payload)/relative).read_bytes()
        destination = web/relative
        if destination.exists() and destination.read_bytes() != data and hashlib.sha256(destination.read_bytes()).hexdigest() != owned.get(relative):
            raise ValueError("New flow file already exists with different changes: "+relative)
        changed[relative] = data
    for relative, data in changed.items():
        save(relative, data)
    print(json.dumps({"backup": str(backup), "distDir": ".next-flow-"+tag, "files": len(manifest)}))


if __name__ == "__main__":
    main()
