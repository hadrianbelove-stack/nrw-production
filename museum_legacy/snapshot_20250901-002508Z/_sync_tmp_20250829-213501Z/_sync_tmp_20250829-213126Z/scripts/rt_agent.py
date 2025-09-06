#!/usr/bin/env python3
import json, re, sys, time, urllib.parse, urllib.request
from html.parser import HTMLParser

UA = {"User-Agent": "Mozilla/5.0 (NRW-rt-agent)"}

class LinkGrab(HTMLParser):
    def __init__(self): super().__init__(); self.links=[]
    def handle_starttag(self, tag, attrs):
        if tag!="a": return
        href=dict(attrs).get("href","")
        if "rottentomatoes.com/m/" in href:
            self.links.append(href)

def _get(url, timeout=15):
    req=urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode("utf-8","ignore")

def search_rt_url(title, year=None):
    # DuckDuckGo HTML endpoint (no key). Keep it polite.
    q = f'site:rottentomatoes.com "{title}"'
    if year: q += f" {year}"
    url = "https://duckduckgo.com/html/?q=" + urllib.parse.quote(q)
    html = _get(url)
    p=LinkGrab(); p.feed(html)
    for href in p.links:
        # normalize absolute URL
        if href.startswith("//"): href = "https:" + href
        if href.startswith("/"): href = "https://www.rottentomatoes.com"+href
        if "/m/" in href and "/trailers" not in href and "/reviews" not in href:
            return href
    return None

def parse_rt_scores(rt_url):
    if not rt_url: return None, None
    html = _get(rt_url)
    # Prefer JSON-LD aggregateRating
    m = re.search(r'"aggregateRating"\s*:\s*{[^}]+}', html)
    critic=None; audience=None
    if m:
        blob=m.group(0)
        p=re.search(r'"ratingValue"\s*:\s*"?(?P<v>\d+)"?', blob)
        if p: critic=int(p.group("v"))
    # Audience score sometimes in Audience Score module
    a=re.search(r'"audienceScore"\s*:\s*{[^}]*"score"\s*:\s*(\d+)', html)
    if a: audience=int(a.group(1))
    return critic, audience

def fetch_rt_for_title(title, year=None, delay=1.0):
    url = search_rt_url(title, year)
    if not url: return None
    time.sleep(delay)
    c,a = parse_rt_scores(url)
    if c is None and a is None: return None
    return {"critic_score": c, "audience_score": a, "rt_url": url, "method": "agent_search"}

if __name__ == "__main__":
    # CLI: scripts/rt_agent.py "Title" 2025
    title = sys.argv[1]
    year  = int(sys.argv[2]) if len(sys.argv)>2 and sys.argv[2].isdigit() else None
    res = fetch_rt_for_title(title, year)
    print(json.dumps(res or {}, indent=2))