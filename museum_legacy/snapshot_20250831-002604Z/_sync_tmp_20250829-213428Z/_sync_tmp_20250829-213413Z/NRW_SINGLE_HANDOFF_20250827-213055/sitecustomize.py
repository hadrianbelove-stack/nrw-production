import os, urllib.parse
if os.getenv("NRW_NO_RT")=="1":
    BLOCK={"rottentomatoes.com","omdbapi.com","query.wikidata.org"}
    try:
        import requests
        _real = requests.sessions.Session.request
        class _DummyResp:
            def __init__(self,u): self.status_code=204; self.headers={}; self.url=u; self.reason="NRW_NO_RT"
            def json(self): return {}
            @property
            def text(self): return ""
            def raise_for_status(self): pass
        def _gate(self, method, url, *a, **k):
            host = urllib.parse.urlparse(url).netloc.lower()
            if any(h in host for h in BLOCK):
                return _DummyResp(url)
            return _real(self, method, url, *a, **k)
        requests.sessions.Session.request = _gate
    except Exception:
        pass
    try:
        import urllib.request
        _uo = urllib.request.urlopen
        class _DummyFile:
            def read(self,*a,**k): return b""
            def __enter__(self): return self
            def __exit__(self,*a): return False
        def _gate_urlopen(url, *a, **k):
            try:
                host = urllib.parse.urlparse(url).netloc.lower()
            except Exception:
                host = ""
            if any(h in host for h in BLOCK):
                return _DummyFile()
            return _uo(url, *a, **k)
        urllib.request.urlopen = _gate_urlopen
    except Exception:
        pass
