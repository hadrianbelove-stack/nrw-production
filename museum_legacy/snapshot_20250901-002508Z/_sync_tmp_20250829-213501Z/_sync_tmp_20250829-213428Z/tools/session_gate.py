
# tools/session_gate.py
import sys, zipfile, hashlib, json, subprocess, os
from pathlib import Path

def sha256_file(p: Path) -> str:
    h=hashlib.sha256()
    with open(p,"rb") as f:
        for chunk in iter(lambda:f.read(1<<20), b""): h.update(chunk)
    return h.hexdigest()

def main():
    if len(sys.argv)<2:
        print("usage: python tools/session_gate.py NRW_SYNC_<timestamp>.zip"); sys.exit(2)
    zip_path = Path(sys.argv[1])
    if not zip_path.exists():
        print("zip not found:", zip_path); sys.exit(2)

    root = Path(".")
    reports = root/"reports"; reports.mkdir(exist_ok=True)
    report = {"ok": True, "issues": [], "zip": zip_path.as_posix()}

    # 1) locate sibling .sha256 if present, else look inside zip
    sha_txt = zip_path.with_suffix(".sha256")
    sha_expected = None
    if sha_txt.exists():
        try:
            sha_expected = (sha_txt.read_text().split()[0]).strip()
        except Exception:
            pass

    # 2) compute actual sha
    sha_actual = sha256_file(zip_path)
    report["sha256_actual"] = sha_actual
    if sha_expected:
        report["sha256_expected"] = sha_expected
        if sha_actual != sha_expected:
            report["ok"] = False
            report["issues"].append("zip sha256 mismatch")

    # 3) extract to restore/
    rdir = root/"restore"/zip_path.stem
    rdir.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(zip_path,"r") as z:
        z.extractall(rdir)

    # 4) run preflight inside restored tree if present
    pf = rdir/"tools"/"preflight.py"
    if pf.exists():
        try:
            p = subprocess.run([sys.executable, str(pf)], cwd=rdir, capture_output=True, text=True, timeout=180)
            report["preflight_stdout"] = p.stdout.strip()
            report["preflight_stderr"] = p.stderr.strip()
            # try to load restored preflight.json
            pr = rdir/"reports"/"preflight.json"
            if pr.exists():
                import json as _json
                restored = _json.loads(pr.read_text())
                report["restored_preflight_ok"] = restored.get("ok", False)
                if not report["restored_preflight_ok"]:
                    report["ok"] = False
                    report["issues"].append("restored preflight failed")
        except Exception as e:
            report["ok"] = False
            report["issues"].append(f"preflight error: {e}")
    else:
        report["issues"].append("no preflight tool in restored tree")

    # 5) drift fingerprint compare if present
    fp_rest = rdir/"reports"/"fingerprint.json"
    if fp_rest.exists():
        try:
            import json as _json, hashlib as _hashlib
            restored = _json.loads(fp_rest.read_text())
            # recompute simple tree hash from restored tree
            def walk_hash(base: Path) -> str:
                paths=[]
                for p in base.rglob("*"):
                    if p.is_file():
                        try:
                            h=_hashlib.sha256(p.read_bytes()).hexdigest()
                        except Exception:
                            h=""
                        rel=p.relative_to(base).as_posix()
                        paths.append(rel+" "+h)
                h=_hashlib.sha256("\n".join(sorted(paths)).encode()).hexdigest()
                return h
            tree = walk_hash(rdir)
            report["fingerprint_tree_restored"] = restored.get("tree_sha256")
            report["fingerprint_tree_recomputed"] = tree
            if restored.get("tree_sha256") and restored["tree_sha256"] != tree:
                report["ok"]=False
                report["issues"].append("fingerprint mismatch in restored tree")
        except Exception as e:
            report["issues"].append(f"fingerprint check error: {e}")

    # 6) write gate report
    out = reports/"session_gate_report.json"
    out.write_text(json.dumps(report, indent=2))
    print(json.dumps(report, indent=2))
    if not report["ok"]:
        sys.exit(1)

if __name__ == "__main__":
    main()
