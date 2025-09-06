from pathlib import Path
import sys, json, time, hashlib, zipfile
from datetime import datetime

root = Path(".")
log  = root/"PROJECT_LOG.md"
ctx  = root/"complete_project_context.md"
reports = root/"reports"; reports.mkdir(exist_ok=True)

def stats():
    total=imdb=posters=rt=0
    try:
        D=json.loads((root/"output/data.json").read_text())
        total=len(D)
        for m in D:
            if m.get("imdb_id"): imdb+=1
            if m.get("poster_url"): posters+=1
            if m.get("rt_score") not in (None,""): rt+=1
    except Exception:
        pass
    return {"total":total,"imdb":imdb,"posters":posters,"rt":rt}

def entries():
    s=stats()
    today = datetime.now().strftime("%Y-%m-%d")
    now_h = datetime.now().strftime("%Y-%m-%d %H:%M")
    log_entry = f"""### SESSION-{today} — End-of-session wrap
Actions
- Provider normalization helpers in generate_site.py
- Poster placeholder + dual asset copy pipeline
- Template normalization (item.*), RT back button only
- TMDb enrichment job
- End-of-Session automation and gated packager; Charter rev 2.2–2.6

Results
- IMDb {s['imdb']}/{s['total']}
- Posters {s['posters']}/{s['total']}
- RT {s['rt']}/{s['total']}

Next
- Ensure OMDB_API_KEY persisted to config.yaml
- Exclusive site rebuild, then RT enrichment
- Build + upload gated single-file handoff"""
    ctx_entry = f"""### SESSION UPDATE — {now_h}
State: IMDb {s['imdb']}/{s['total']}, Posters {s['posters']}/{s['total']}, RT {s['rt']}/{s['total']}.
Workflow: Charter rev 2.2–2.6 in effect (single-file handoff, code-block rules, session-end gate, auto wrap-up)."""
    return log_entry, ctx_entry, today

def has_today(p:Path, token:str, today:str)->bool:
    if not p.exists(): return False
    s=p.read_text()
    return (today in s) and (token in s)

def write_proposal():
    L,C,today = entries()
    (reports/"session_end_proposal.md").write_text("# Proposed session updates\n\n"+L+"\n\n"+C+"\n")
    (reports/"session_end_report.json").write_text(json.dumps({"ok":False,"reason":"pending approval"}, indent=2))
    print((reports/"session_end_proposal.md").as_posix())

def apply_updates():
    L,C,today = entries()
    for p,text in ((log,L),(ctx,C)):
        if p.exists() and not p.read_text().endswith("\n"):
            p.write_text(p.read_text()+"\n")
        p.write_text((p.read_text() if p.exists() else "") + ("\n" if p.exists() and p.read_text().strip() else "") + text + "\n")
    (reports/"session_end_report.json").write_text(json.dumps({"ok":True,"applied":True}, indent=2))
    print("applied")

def check_only():
    _,_,today = entries()
    ok = has_today(log,"SESSION-",today) and has_today(ctx,"SESSION UPDATE",today)
    (reports/"session_end_report.json").write_text(json.dumps({"ok":ok}, indent=2))
    print("ok" if ok else "missing")
    sys.exit(0 if ok else 1)

def build_zip():
    ts=time.strftime("%Y%m%d-%H%M%S")
    z=f"NRW_SYNC_{ts}.zip"; man=f"NRW_SYNC_{ts}.manifest.txt"; sha=f"NRW_SYNC_{ts}.sha256"
    skip=(".venv/",".git/","__pycache__/","tmp/","NRW_SYNC_")
    def keep(p:Path):
        s=p.as_posix()
        return p.is_file() and not any(s.startswith(x) or f"/{x}" in s for x in skip)
    files=[p for p in root.rglob("*") if keep(p)]
    with open(man,"w") as m:
        for p in sorted(files): m.write(p.as_posix()+"\n")
    with zipfile.ZipFile(z,"w",zipfile.ZIP_DEFLATED) as Z:
        for p in files: Z.write(p,p.as_posix())
        Z.write(man,man)
    h=hashlib.sha256(open(z,"rb").read()).hexdigest()
    open(sha,"w").write(f"{h}  {z}\n")
    print(z); print(man); print(sha)

if __name__=="__main__":
    arg = sys.argv[1] if len(sys.argv)>1 else "--auto"
    if arg=="--propose": write_proposal(); sys.exit(0)
    if arg=="--apply":   apply_updates(); sys.exit(0)
    if arg=="--check":   check_only()
    if arg=="--package": build_zip(); sys.exit(0)
    if arg=="--auto":
        write_proposal(); apply_updates(); check_only(); build_zip(); sys.exit(0)
    print("usage: python tools/session_end.py [--propose|--apply|--check|--package|--auto]"); sys.exit(2)
