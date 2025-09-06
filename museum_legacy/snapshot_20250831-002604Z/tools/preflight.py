
# tools/preflight.py
import hashlib, json, re, sys
from pathlib import Path

root = Path(".")
report = {"ok": True, "issues": [], "tips": []}

def sha256_path(p: Path) -> str:
    import hashlib
    h=hashlib.sha256()
    with open(p,"rb") as f:
        for chunk in iter(lambda:f.read(65536), b""): h.update(chunk)
    return h.hexdigest()

# Charter checks
cpath = next((p for p in [root/"PROJECT_CHARTER.md", root/"docs/PROJECT_CHARTER.md"] if p.exists()), None)
if not cpath:
    report["ok"]=False; report["issues"].append("Charter missing (PROJECT_CHARTER.md).")
else:
    text=cpath.read_text(errors="ignore")
    report["charter_sha256"]=sha256_path(cpath)
    if "Workflow Protocol (rev 2)" not in text:
        report["ok"]=False; report["issues"].append("Charter missing Workflow Protocol (rev 2).")
    if not (("No-Drift UI Changes" in text) or re.search(r"No[ -]?Drift UI Changes", text)):
        report["ok"]=False; report["issues"].append("Charter missing No-Drift UI clause.")

# Template invariants
tpath = root/"templates/site_enhanced.html"
if not tpath.exists():
    report["ok"]=False; report["issues"].append("Template templates/site_enhanced.html not found.")
else:
    s=tpath.read_text(errors="ignore")
    if not re.search(r'class="card-back-link".*href="\{\{\s*item\.amazon_url', s, re.S):
        report["ok"]=False; report["issues"].append("Card-back overlay href not bound to item.amazon_url fallback chain.")
    if not re.search(r'class="[^"]*\bbtn-rt\b[^"]*".*href="\{\{\s*item\.rt_url\s*\}\}"', s, re.S):
        report["ok"]=False; report["issues"].append("RT button href not bound to item.rt_url.")
    if re.search(r'\brt-badge\b', s):
        report["issues"].append("Front RT badge present (should be removed).")
    if not (('item.runtime_minutes|string' in s) and ('item.studio or "—"' in s)):
        report["ok"]=False; report["issues"].append("Meta fallbacks for runtime/studio missing.")

# TMDb credentials presence (no network)
import yaml, os
creds={"bearer": os.getenv("TMDB_BEARER"), "api_key": os.getenv("TMDB_API_KEY")}
try:
    if (root/"config.yaml").exists():
        cfg=yaml.safe_load(open(root/"config.yaml")) or {}
        tm=cfg.get("tmdb") or {}
        creds["bearer"]=creds["bearer"] or tm.get("bearer")
        creds["api_key"]=creds["api_key"] or tm.get("api_key")
except Exception:
    pass
if not (creds["bearer"] or creds["api_key"]):
    report["issues"].append("TMDb credentials missing (TMDB_BEARER or TMDB_API_KEY).")
    report["tips"].append("Set TMDB_BEARER or TMDB_API_KEY, and persist into config.yaml.")

# Output
out = root/"reports"; out.mkdir(exist_ok=True)
(out/"preflight.json").write_text(json.dumps(report, indent=2))
print(json.dumps(report, indent=2))
