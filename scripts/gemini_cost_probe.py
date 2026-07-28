#!/usr/bin/env python3
"""
Gemini cost probe — measure real token usage + $/call for each NRW Gemini scraper
under different models and thinking budgets, so we can pick the cheapest config that
still holds quality.

  Plan: ~/.claude/plans/goofy-booping-canyon.md (methodically cut the Gemini bill)

WHY THIS EXISTS
  Jul 2026 Google Cloud bill = $200/mo, ~all Gemini, driven by Gemini 2.5 Pro OUTPUT
  tokens. Root causes: every scraper is hardcoded to Pro (base.py:217) and capsules
  run Pro at a 32,768-token thinking budget x 3 variants (capsule.py:879). Thinking
  tokens bill as output. Before changing anything we MEASURE.

NON-INVASIVE — this script:
  * uses a throwaway temp cache dir (never reads/writes cache/*.json)
  * calls finder methods directly (never the write_capsule.py --batch path)
  * never writes data.json / data_archive.json / movie_tracking.*
  * only output = metrics/gemini_cost_probe_<stamp>.{csv,md}

COST + REQUIREMENTS
  Makes REAL, paid Gemini calls. Needs GEMINI_API_KEY set and billing ENABLED on the
  Google Cloud project. A full run is ~$3-6 one-time. Sanity-check first with a subset:
      /usr/bin/python3 scripts/gemini_cost_probe.py --only capsule --limit 2
  Then the full run:
      /usr/bin/python3 scripts/gemini_cost_probe.py

The per-call token counts are ground truth. The $ figures use the PRICING table below
— confirm current Gemini 2.5 rates before quoting dollars to anyone.
"""

import argparse
import csv
import inspect
import json
import os
import random
import re
import shutil
import sys
import tempfile
import time
from datetime import datetime

# Run from repo root regardless of cwd
REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(REPO)
sys.path.insert(0, REPO)

import load_env  # noqa: F401  (loads .env -> os.environ, incl. GEMINI_API_KEY)

# --------------------------------------------------------------------------- #
# Pricing — USD per 1,000,000 tokens. CONFIRM against current Google pricing.  #
# Thinking ("thoughts") tokens are billed at the OUTPUT rate.                  #
# Pro rates are the <=200k-prompt tier (all our prompts are well under 200k).  #
# --------------------------------------------------------------------------- #
PRICING = {
    'gemini-2.5-pro':   {'in': 1.25, 'out': 10.00},
    'gemini-2.5-flash': {'in': 0.30, 'out': 2.50},
}

PRO = 'gemini-2.5-pro'
FLASH = 'gemini-2.5-flash'

# Config = (label, model, thinking).  thinking is one of:
#   'keep'    -> don't touch whatever the finder itself sets (baseline)
#   'dynamic' -> thinking_budget = -1 (model decides)
#   'off'     -> thinking_budget = 0  (Flash/Flash-Lite only; Pro cannot disable)
#   <int>     -> fixed thinking_budget
CAPSULE_CONFIGS = [
    ('pro-32k (current)', PRO,   'keep'),      # keep == the hardcoded 32768
    ('pro-8k',            PRO,   8192),
    ('pro-4k',            PRO,   4096),
    ('pro-dynamic',       PRO,   'dynamic'),
    ('flash-dynamic',     FLASH, 'dynamic'),
    ('flash-thinkoff',    FLASH, 'off'),
]

LOOKUP_CONFIGS = [
    ('pro (current)',   PRO,   'keep'),
    ('flash-dynamic',   FLASH, 'dynamic'),
    ('flash-thinkoff',  FLASH, 'off'),
]


def cost_usd(model, prompt_tok, output_tok, thoughts_tok):
    r = PRICING[model]
    return prompt_tok / 1e6 * r['in'] + (output_tok + thoughts_tok) / 1e6 * r['out']


# --------------------------------------------------------------------------- #
# Meter: wrap a finder's _generate to (a) force model, (b) override thinking,  #
# (c) capture usage_metadata for every underlying generate_content call.       #
# All finders route through GeminiFinderBase._generate, so this covers them.   #
# --------------------------------------------------------------------------- #
class Meter:
    def __init__(self, finder, model, thinking):
        self.finder = finder
        self.model = model
        self.thinking = thinking
        self.calls = []          # one dict per underlying generate_content call
        self._orig = None

    def __enter__(self):
        self._orig = self.finder._generate
        meter = self

        def patched(contents, config=None):
            types = meter.finder.types  # set by _init_gemini before any _generate
            if config is None:
                config = types.GenerateContentConfig()
            tc = meter._thinking_config(types)
            if tc is not None:
                config = config.model_copy(update={'thinking_config': tc})
            saved_model = meter.finder.model_name
            meter.finder.model_name = meter.model
            t0 = time.time()
            try:
                resp = meter._orig(contents, config=config)
            finally:
                meter.finder.model_name = saved_model
            um = getattr(resp, 'usage_metadata', None)
            meter.calls.append({
                'prompt':   int(getattr(um, 'prompt_token_count', 0) or 0),
                'output':   int(getattr(um, 'candidates_token_count', 0) or 0),
                'thoughts': int(getattr(um, 'thoughts_token_count', 0) or 0),
                'total':    int(getattr(um, 'total_token_count', 0) or 0),
                'seconds':  round(time.time() - t0, 2),
            })
            return resp

        self.finder._generate = patched
        return self

    def __exit__(self, *exc):
        self.finder._generate = self._orig

    def _thinking_config(self, types):
        if self.thinking == 'keep':
            return None
        if self.thinking == 'off':
            budget = 0
        elif self.thinking == 'dynamic':
            budget = -1
        else:
            budget = int(self.thinking)
        return types.ThinkingConfig(thinking_budget=budget)

    def totals(self):
        p = sum(c['prompt'] for c in self.calls)
        o = sum(c['output'] for c in self.calls)
        t = sum(c['thoughts'] for c in self.calls)
        return {
            'calls': len(self.calls),
            'prompt': p, 'output': o, 'thoughts': t,
            'total': p + o + t,
            'seconds': round(sum(c['seconds'] for c in self.calls), 2),
            'cost': cost_usd(self.model, p, o, t),
        }


# --------------------------------------------------------------------------- #
# Sample selection — pull a varied spread from data.json                        #
# --------------------------------------------------------------------------- #
def _imdb_id(film):
    url = (film.get('links') or {}).get('imdb') or ''
    m = re.search(r'(tt\d+)', url)
    return m.group(1) if m else None


def _film_type(film):
    f = film.get('filters') or {}
    if film.get('is_slop'):
        return 'slop'
    if film.get('_reissue') or film.get('reissue_label') or f.get('is_restoration'):
        return 'reissue'
    if f.get('is_documentary') or 'Documentary' in (film.get('genres') or []):
        return 'documentary'
    if f.get('is_series'):
        return 'series'
    if f.get('is_foreign') or (film.get('original_language') not in (None, 'en')):
        return 'foreign'
    if len((film.get('title') or '')) <= 4:
        return 'short-title'
    return 'english'


def select_sample(limit):
    data = json.load(open('data.json'))
    movies = [m for m in data['movies'] if m.get('synopsis') and m.get('title')]
    buckets = {}
    for m in movies:
        buckets.setdefault(_film_type(m), []).append(m)
    # Prefer one of each type, richest (has director + imdb) first, then fill.
    order = ['english', 'foreign', 'documentary', 'reissue', 'slop',
             'series', 'short-title']
    picked, seen = [], set()

    def richness(m):
        c = m.get('crew') or {}
        return (bool(c.get('director')), bool(_imdb_id(m)), bool(m.get('notability')))

    for t in order:
        cands = sorted(buckets.get(t, []), key=richness, reverse=True)
        if cands:
            picked.append(cands[0]); seen.add(str(cands[0]['id']))
        if len(picked) >= limit:
            break
    # Fill remaining slots with the richest unused films across all buckets
    if len(picked) < limit:
        rest = sorted([m for m in movies if str(m['id']) not in seen],
                      key=richness, reverse=True)
        for m in rest:
            picked.append(m); seen.add(str(m['id']))
            if len(picked) >= limit:
                break
    return picked[:limit]


# --------------------------------------------------------------------------- #
# Temp-cache finder factories (never touch cache/*.json)                        #
# --------------------------------------------------------------------------- #
def _tmp(cache_dir, name):
    return os.path.join(cache_dir, name)


def make_finders(cache_dir):
    """Return {category_key: (label, factory, method_name)} for the lookup finders."""
    from gemini_scraper.imdb import GeminiIMDbFinder
    from gemini_scraper.wikipedia import GeminiWikipediaFinder
    from gemini_scraper.vod_date import GeminiVODDateFinder
    from gemini_scraper.youtube import GeminiYouTubeFinder
    from gemini_scraper.restoration_vod import GeminiRestorationVODFinder
    return {
        'imdb':        ('IMDb rating',   lambda: GeminiIMDbFinder(_tmp(cache_dir, 'imdb.json')),        'find_rating'),
        'wikipedia':   ('Wikipedia URL', lambda: GeminiWikipediaFinder(_tmp(cache_dir, 'wiki.json')),   'find_wikipedia_url'),
        'vod_date':    ('VOD date',      lambda: GeminiVODDateFinder(_tmp(cache_dir, 'vod.json')),       'find_vod_date'),
        'youtube':     ('YouTube trailer', lambda: GeminiYouTubeFinder(_tmp(cache_dir, 'yt.json')),      'find_trailer'),
        'restoration': ('Restoration VOD', lambda: GeminiRestorationVODFinder(_tmp(cache_dir, 'rest.json')), 'find_restoration_vod_status'),
    }


def _film_kwargs(film):
    """Superset of kwargs; each finder method gets only the ones it accepts."""
    crew = film.get('crew') or {}
    return {
        'title': film.get('title'),
        'year': film.get('year'),
        'imdb_id': _imdb_id(film),
        'director': crew.get('director'),
        'original_title': film.get('original_title'),
        'country': film.get('country'),
    }


def _call_with_accepted(method, kwargs):
    sig = inspect.signature(method)
    accepted = {k: v for k, v in kwargs.items() if k in sig.parameters and v is not None}
    return method(**accepted)


# --------------------------------------------------------------------------- #
# Runners                                                                       #
# --------------------------------------------------------------------------- #
def run_lookups(sample, cache_dir, rows):
    finders = make_finders(cache_dir)
    for key, (label, factory, method_name) in finders.items():
        print(f"\n=== LOOKUP: {label} ===")
        for film in sample:
            baseline_out = None
            for cfg_label, model, thinking in LOOKUP_CONFIGS:
                # Fresh finder per config so an empty temp cache forces a live call.
                finder = factory()
                if not finder._init_gemini():
                    print("  !! Gemini init failed (key/billing?) — aborting.")
                    return
                # wipe temp cache so nothing is served from a prior config
                finder.cache = {}
                method = getattr(finder, method_name)
                kwargs = _film_kwargs(film)
                out = None
                try:
                    with Meter(finder, model, thinking) as meter:
                        out = _call_with_accepted(method, kwargs)
                    tot = meter.totals()
                except Exception as e:
                    print(f"  {film['title'][:28]:28} {cfg_label:16} ERROR {e}")
                    continue
                out_str = str(out)[:80] if out is not None else ''
                if cfg_label == LOOKUP_CONFIGS[0][0]:
                    baseline_out = out_str
                match = '' if cfg_label == LOOKUP_CONFIGS[0][0] else (
                    'MATCH' if out_str == baseline_out else 'DIFF')
                print(f"  {film['title'][:28]:28} {cfg_label:16} "
                      f"${tot['cost']:.4f}  tok={tot['total']:<6} think={tot['thoughts']:<5} {match}")
                rows.append({
                    'category': key, 'scraper': label,
                    'film_id': film['id'], 'film': film['title'], 'film_type': _film_type(film),
                    'config': cfg_label, 'model': model, 'thinking': thinking,
                    'calls': tot['calls'], 'prompt_tok': tot['prompt'],
                    'output_tok': tot['output'], 'thoughts_tok': tot['thoughts'],
                    'total_tok': tot['total'], 'cost_usd': round(tot['cost'], 5),
                    'seconds': tot['seconds'], 'output_preview': out_str,
                    'match_baseline': match,
                })


def run_capsules(sample, cache_dir, rows, capsule_texts, variants):
    from gemini_scraper.capsule import GeminiCapsuleWriter
    for film in sample:
        crew = film.get('crew') or {}
        base_kwargs = dict(
            title=film.get('title'), year=film.get('year'),
            director=crew.get('director'), cast=crew.get('cast'),
            genres=film.get('genres'), runtime=film.get('runtime'),
            synopsis=film.get('synopsis'), rt_score=film.get('rt_score'),
            imdb_rating=film.get('imdb_rating'),
            country=film.get('country'), original_language=film.get('original_language'),
            original_title=film.get('original_title'), studio=film.get('studio'),
            wiki_url=(film.get('links') or {}).get('wikipedia'),
            force=True, skip_verify=True, variants=variants,
        )
        print(f"\n=== CAPSULE: {film['title']} ({film.get('year')}) [{_film_type(film)}] ===")
        for cfg_label, model, thinking in CAPSULE_CONFIGS:
            writer = GeminiCapsuleWriter(_tmp(cache_dir, f"cap_{cfg_label}.json"))
            if not writer._init_gemini():
                print("  !! Gemini init failed (key/billing?) — aborting.")
                return
            writer.cache = {}
            try:
                with Meter(writer, model, thinking) as meter:
                    result = writer.write_capsule(**base_kwargs)
                tot = meter.totals()
            except Exception as e:
                print(f"  {cfg_label:16} ERROR {e}")
                continue
            caps = (result or {}).get('capsules') or ([result.get('capsule')] if result and result.get('capsule') else [])
            print(f"  {cfg_label:16} ${tot['cost']:.4f}  tok={tot['total']:<6} "
                  f"think={tot['thoughts']:<6} calls={tot['calls']} {tot['seconds']}s")
            rows.append({
                'category': 'capsule', 'scraper': 'Capsule',
                'film_id': film['id'], 'film': film['title'], 'film_type': _film_type(film),
                'config': cfg_label, 'model': model, 'thinking': thinking,
                'calls': tot['calls'], 'prompt_tok': tot['prompt'],
                'output_tok': tot['output'], 'thoughts_tok': tot['thoughts'],
                'total_tok': tot['total'], 'cost_usd': round(tot['cost'], 5),
                'seconds': tot['seconds'],
                'output_preview': (caps[0][:80] if caps else ''),
                'match_baseline': '',
            })
            capsule_texts.append({
                'film': f"{film['title']} ({film.get('year')})",
                'config': cfg_label, 'capsules': caps, 'cost': round(tot['cost'], 5),
            })


# --------------------------------------------------------------------------- #
# Reporting                                                                     #
# --------------------------------------------------------------------------- #
def write_csv(rows, path):
    if not rows:
        return
    cols = ['category', 'scraper', 'film_id', 'film', 'film_type', 'config', 'model',
            'thinking', 'calls', 'prompt_tok', 'output_tok', 'thoughts_tok',
            'total_tok', 'cost_usd', 'seconds', 'match_baseline', 'output_preview']
    with open(path, 'w', newline='') as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        for r in rows:
            w.writerow(r)


def write_markdown(rows, capsule_texts, path, monthly_films, variants):
    lines = []
    lines.append(f"# Gemini cost probe — {datetime.now().isoformat(timespec='minutes')}")
    lines.append("")
    lines.append(f"Sample films run under each config. Monthly projection assumes "
                 f"**{monthly_films} new films/month** and **{variants} capsule variants**. "
                 f"Token counts are exact; $ uses the PRICING table (confirm rates).")
    lines.append("")

    # --- Average cost per config, per scraper ---
    agg = {}
    for r in rows:
        k = (r['scraper'], r['config'], r['model'])
        a = agg.setdefault(k, {'cost': 0.0, 'n': 0, 'think': 0, 'tok': 0})
        a['cost'] += r['cost_usd']; a['n'] += 1
        a['think'] += r['thoughts_tok']; a['tok'] += r['total_tok']
    lines.append("## Average cost per call, by scraper x config")
    lines.append("")
    lines.append("| Scraper | Config | Model | Avg $/call | Avg tokens | Avg thinking | Proj. $/mo* |")
    lines.append("|---|---|---|---:|---:|---:|---:|")
    for (scraper, config, model), a in sorted(agg.items()):
        avg = a['cost'] / a['n']
        # capsule cost is per film; lookups are per film too (1 call/film category)
        proj = avg * monthly_films
        lines.append(f"| {scraper} | {config} | {model} | ${avg:.4f} | "
                     f"{a['tok']//a['n']} | {a['think']//a['n']} | ${proj:.2f} |")
    lines.append("")
    lines.append("*Rough: assumes every new film hits this scraper once/month. "
                 "Lookups may run on more/fewer films than capsules; treat as a per-scraper ceiling.")
    lines.append("")

    # --- Blind capsule side-by-side (for quality judging) ---
    if capsule_texts:
        lines.append("## Capsule quality — blind side-by-side")
        lines.append("")
        lines.append("Judge the writing WITHOUT looking at the key at the bottom. "
                     "Note which letters read best; then check the key to see which are cheap.")
        lines.append("")
        by_film = {}
        for c in capsule_texts:
            by_film.setdefault(c['film'], []).append(c)
        rng = random.Random(42)
        key_lines = []
        for film, entries in by_film.items():
            lines.append(f"### {film}")
            lines.append("")
            shuffled = entries[:]
            rng.shuffle(shuffled)
            labels = [chr(ord('A') + i) for i in range(len(shuffled))]
            for lab, e in zip(labels, shuffled):
                txt = (e['capsules'][0] if e['capsules'] else '(none)')
                lines.append(f"**{lab}.** {txt}")
                lines.append("")
                key_lines.append(f"- {film} — {lab} = `{e['config']}` (${e['cost']:.4f})")
        lines.append("---")
        lines.append("")
        lines.append("<details><summary>KEY (which letter was which config)</summary>")
        lines.append("")
        lines.extend(key_lines)
        lines.append("")
        lines.append("</details>")
    with open(path, 'w') as f:
        f.write("\n".join(lines) + "\n")


# --------------------------------------------------------------------------- #
def main():
    ap = argparse.ArgumentParser(description="Measure Gemini scraper cost per config.")
    ap.add_argument('--limit', type=int, default=8, help='Number of sample films (default 8)')
    ap.add_argument('--only', choices=['lookups', 'capsule', 'all'], default='all',
                    help='Run only one category (default all)')
    ap.add_argument('--variants', type=int, default=2, help='Capsule variants per config (default 2)')
    ap.add_argument('--monthly-films', type=int, default=120,
                    help='New films/month for the $/mo projection (default 120)')
    ap.add_argument('--ids', help='Comma-separated movie IDs to force the sample')
    args = ap.parse_args()

    if not os.environ.get('GEMINI_API_KEY'):
        print("GEMINI_API_KEY not set. This probe needs a live key + billing ON.")
        sys.exit(1)

    if args.ids:
        wanted = set(args.ids.split(','))
        allm = json.load(open('data.json'))['movies']
        sample = [m for m in allm if str(m['id']) in wanted]
    else:
        sample = select_sample(args.limit)

    print(f"Sample ({len(sample)} films):")
    for m in sample:
        print(f"  [{_film_type(m):12}] {m['title']} ({m.get('year')})  id={m['id']}")
    print("\nThis makes REAL paid Gemini calls. Ctrl-C now to abort.\n")

    cache_dir = tempfile.mkdtemp(prefix='gemini_probe_')
    rows, capsule_texts = [], []
    try:
        if args.only in ('lookups', 'all'):
            run_lookups(sample, cache_dir, rows)
        if args.only in ('capsule', 'all'):
            run_capsules(sample, cache_dir, rows, capsule_texts, args.variants)
    finally:
        shutil.rmtree(cache_dir, ignore_errors=True)

    os.makedirs('metrics', exist_ok=True)
    stamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    csv_path = f'metrics/gemini_cost_probe_{stamp}.csv'
    md_path = f'metrics/gemini_cost_probe_{stamp}.md'
    write_csv(rows, csv_path)
    write_markdown(rows, capsule_texts, md_path, args.monthly_films, args.variants)
    print(f"\nWrote:\n  {csv_path}\n  {md_path}")
    print("Review the .md (blind capsule comparison + cost table), then we pick a config.")


if __name__ == '__main__':
    main()
