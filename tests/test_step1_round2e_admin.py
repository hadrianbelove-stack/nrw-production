"""Round 2e, admin group: the tests that keep the round-2e admin fixes in place.

Owner's rules these protect (binding):
  1. A film held as "not out yet" is a WAIT, never a drop; every held film is re-checked every run.
  5. Remove and Revert are OPPOSITE. Remove = never wanted, permanent. Revert = wrongly marked new:
     off the wall now, back ON ITS OWN the day it's really out.
  And the day's CI work (new arrivals, put-backs, "not out yet" days) must reach GitHub intact.

Round-2e changes under test (round-2d review finding -> change):
  EO-1  pipeline/tracking_db.py: get_tracking_db() re-reads movie_tracking.json when a `git pull`
        made it newer than the DB (resync_if_stale); save_all stamps the DB after its own export.
        Without it a long-running admin pushed its old tracking copy over CI's day of work.
  CRIT-4 admin/routes/movies.py: Revert refuses (changes nothing) while today's GitHub update
        (daily-check.yml) is queued or running (_daily_update_running via `gh run list`; None ->
        goes ahead). .claude/commands/revert.md Step 1 says the same for the CLI path.
  EO-3  admin/routes/curate_flow.py _git_commit_push: "nothing to commit" while local main is ahead
        of origin/main pushes, instead of reporting success.
  EO-4 / REV-3  admin Add: a reverted film's hidden entry gets a clear refusal; re-adding an existing
        tracking record clears the owner-revert keys.
  EO-2  scripts/add_movie.py: re-adding an existing wall entry pops `hidden` / `_jw_unconfirmed` and
        the revert keys; .claude/commands/add-movie.md's duplicate check says REVERTED/HIDDEN is
        safe to add.

Harnesses (all real code, only the network and the clock faked; no test touches a real checkout):
  * `world` (tests/test_step1_holds_and_dates.py): the v2 pipeline in a tmp dir, write guard on every
    NRW checkout. Harlem = a verbatim 78303fd6 tracking record (Once Upon a Time in Harlem).
  * `nrw` (tests/test_step1_enrichment.py): the same idea for enrichment; Beware Boiuna = verbatim
    78303fd6 rows. The real scripts/revert_movie.py and scripts/add_movie.py run in it.
  * EO-1 / EO-3: throwaway git repos built in pytest's tmp dir -- a bare "GitHub" remote, the owner's
    checkout and a CI clone -- with production's REAL data files (`git show 16150a67:` = production
    data on 2026-11-14, `git show d86def0a:` = CI's real daily commit of 2026-11-15: 41 tracking
    records added, 79 changed, 3 films put on the wall). git runs only inside those repos, with a
    private git config (GIT_CONFIG_GLOBAL), never against a real repository. `gh` is never called:
    admin.routes.movies._daily_update_running is always replaced (the CRIT-4 unit test replaces
    subprocess.run instead).

Run: cd <worktree> && /usr/bin/python3 -m pytest tests/test_step1_round2e_admin.py -q -p no:cacheprovider
"""
import contextlib
import copy
import io
import json
import logging
import os
import re
import socket
import subprocess
import sys
import time
from datetime import datetime as _REAL_DATETIME, timezone
from functools import lru_cache

import pytest

sys.dont_write_bytecode = True
TESTS = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(TESTS)
if TESTS not in sys.path:
    sys.path.insert(0, TESTS)

import test_step1_holds_and_dates as h  # noqa: E402
import test_step1_enrichment as e  # noqa: E402
from test_step1_holds_and_dates import world  # noqa: E402,F401  (fixture)
from test_step1_enrichment import nrw  # noqa: E402,F401  (fixture)
from test_step1_revert import _cinema, Q, INCONCLUSIVE, HARLEM_APPLE  # noqa: E402

putback = h.putback
HARLEM, BEWARE = h.HARLEM, e.BEWARE

# Every key an owner Revert leaves on a tracking record that marks it "the owner's revert".
REVERT_KEYS = ('_jw_revert_reason', '_jw_reverted_at', '_jw_reverted', '_reverted_from_available',
               '_reverted_by_owner', '_reverted_by_owner_at', '_added_manually_before_revert',
               '_revert_page_preorder')

P_DATA = '16150a67'   # production's data files, 2026-11-14 ("Daily NRW Update - 2026-11-14")
CI_DATA = 'd86def0a'  # CI's real daily commit of 2026-11-15 ("Daily NRW Update - 2026-11-15")

for _name in ('admin', 'data_generator'):
    logging.getLogger(_name).addHandler(logging.NullHandler())


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def _no_gh(*a, **k):
    pytest.fail('a test asked GitHub (gh) whether the daily update runs')


def _no_git(files, message):
    pytest.fail('a test ran git from the admin outside a throwaway repo')


def _admin_app(monkeypatch, clock_module=None, publish=_no_git, update_running=_no_gh):
    """The REAL admin app (admin.create_app). The owner types the title (no TMDB lookup); git and gh
    are replaced unless a test passes its own stand-ins. Imported lazily: the admin's logger setup
    makes a logs/ folder in the current directory, which must be the tmp checkout."""
    lg = logging.getLogger('admin')
    monkeypatch.setattr(lg, 'handlers', [logging.NullHandler()])
    monkeypatch.setattr(lg, 'propagate', False)
    import admin.routes.movies as movies_mod
    import admin.routes.curate_flow as curate_flow
    monkeypatch.setattr(movies_mod, 'get_tmdb_api_key', lambda: None)
    if clock_module is not None:
        monkeypatch.setattr(movies_mod, 'datetime', clock_module.datetime)
    if publish is not None:
        monkeypatch.setattr(curate_flow, '_git_commit_push', publish)
        # No real git here: nor the Revert's catch-up with GitHub (round 2f; it runs git itself).
        # With publish=None (throwaway repos + bare remote) the real one runs, offline.
        monkeypatch.setattr(movies_mod, '_catch_up_with_github', lambda: None, raising=False)
    # raising=False: round 2d has no _daily_update_running (the test then shows what 2d does)
    monkeypatch.setattr(movies_mod, '_daily_update_running', update_running, raising=False)
    from admin import create_app
    app = create_app()
    app.config['TESTING'] = True
    return app.test_client()


def _revert_md():
    with open(os.path.join(ROOT, '.claude', 'commands', 'revert.md')) as f:
        return f.read()


def _add_movie_md_duplicate_check(mid):
    """Run .claude/commands/add-movie.md Step 3 -- the doc's own python snippet, extracted from the
    file -- in the current (tmp) checkout, and return what it prints."""
    with open(os.path.join(ROOT, '.claude', 'commands', 'add-movie.md')) as f:
        doc = f.read()
    step3 = doc[doc.index('## Step 3'):doc.index('## Step 4')]
    code = re.search(r'/usr/bin/python3 -c "\n(.*?)\n"\n```', step3, re.S).group(1)
    code = code.replace('\\"', '"').replace('$TMDB_ID', str(mid))
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        exec(compile(code, 'add-movie.md Step 3', 'exec'), {})
    return buf.getvalue().strip()


def _site_shows(entry):
    """assets/app.js:106-110: the site drops hidden, 'reverted' and undated entries."""
    return bool(entry) and not entry.get('hidden') and entry.get('_enrichment_status') != 'reverted' \
        and bool(entry.get('digital_date'))


# ---------------------------------------------------------------------------
# Throwaway git repos: a bare "GitHub", the owner's checkout, a CI clone
# ---------------------------------------------------------------------------

def _clean_env():
    env = {k: v for k, v in os.environ.items() if not k.startswith('GIT_')}
    env['GIT_CONFIG_NOSYSTEM'] = '1'
    return env


@lru_cache(maxsize=None)
def _real_file(rev, path):
    """A data file as production committed it (read-only `git show`; objects via alternates)."""
    r = subprocess.run(['git', '-C', ROOT, 'show', f'{rev}:{path}'], capture_output=True, env=_clean_env())
    assert r.returncode == 0, r.stderr.decode()[-300:]
    return r.stdout.decode('utf-8')


def _real_json(rev, path):
    return json.loads(_real_file(rev, path))


class Repos:
    """GitHub (a bare repo), the owner's checkout (`site`, where the admin runs) and CI's clone."""

    def __init__(self, tmp, monkeypatch):
        self.tmp = str(tmp)
        self.remote = os.path.join(self.tmp, 'github.git')
        self.site = os.path.join(self.tmp, 'site')
        self.ci = os.path.join(self.tmp, 'ci')
        self.hook_log = os.path.join(self.tmp, 'pushes_seen_by_github.log')
        cfg = os.path.join(self.tmp, 'gitconfig')
        with open(cfg, 'w') as f:
            f.write('[user]\n\tname = owner\n\temail = owner@example.invalid\n[commit]\n\tgpgsign = false\n'
                    '[init]\n\tdefaultBranch = main\n[pull]\n\trebase = false\n')
        # Every git process (the test's and the admin's own _git_commit_push) uses only this config.
        for k in [k for k in os.environ if k.startswith('GIT_')]:
            monkeypatch.delenv(k)
        monkeypatch.setenv('GIT_CONFIG_GLOBAL', cfg)
        monkeypatch.setenv('GIT_CONFIG_NOSYSTEM', '1')
        self.env = {**os.environ}

    def git(self, cwd, *args, check=True):
        assert os.path.realpath(cwd).startswith(os.path.realpath(self.tmp)), cwd
        r = subprocess.run(['git', *args], cwd=cwd, capture_output=True, text=True, env=self.env)
        if check:
            assert r.returncode == 0, f'git {args}: {r.stdout}{r.stderr}'
        return (r.stdout + r.stderr).strip()

    def create(self, files):
        """GitHub holds `files` ({name: text}); the owner's checkout is a clone of it."""
        os.makedirs(self.site)
        self.git(self.tmp, 'init', '-q', '--bare', self.remote)
        self.git(self.remote, 'symbolic-ref', 'HEAD', 'refs/heads/main')
        self.git(self.site, 'init', '-q', '-b', 'main')
        nohooks = os.path.join(self.tmp, 'no-hooks')
        os.makedirs(nohooks)
        self.git(self.site, 'config', 'core.hooksPath', nohooks)
        for name, text in files.items():
            with open(os.path.join(self.site, name), 'w', encoding='utf-8') as f:
                f.write(text)
        with open(os.path.join(self.site, '.gitignore'), 'w') as f:
            # The site's real ignore rules (the admin's data.json.backup.* files, *.tmp exports,
            # logs/, admin/.pending_changes, the tracking DB): git's "nothing to commit" wording
            # depends on what is left untracked.
            f.write(_real_file(P_DATA, '.gitignore'))
        self.git(self.site, 'add', '-A')
        self.git(self.site, 'commit', '-q', '-m', 'production data')
        self.git(self.site, 'remote', 'add', 'origin', self.remote)
        self.git(self.site, 'push', '-q', '-u', 'origin', 'main')

    def github_refuses_pushes(self, refuse=True):
        """A pre-receive hook on GitHub that refuses every push (an outage, expired credentials).
        Every push that reaches GitHub is logged either way."""
        hook = os.path.join(self.remote, 'hooks', 'pre-receive')
        with open(hook, 'w') as f:
            f.write(f'#!/bin/sh\necho push >> "{self.hook_log}"\n'
                    + ('echo "remote: refusing every push (test)"\nexit 1\n' if refuse else 'exit 0\n'))
        os.chmod(hook, 0o755)

    def pushes_seen(self):
        if not os.path.exists(self.hook_log):
            return 0
        with open(self.hook_log) as f:
            return len(f.read().split())

    def github_json(self, name):
        return json.loads(self.git(self.remote, 'show', f'main:{name}'))

    def unpublished_commits(self):
        self.git(self.site, 'fetch', '-q', 'origin')
        return int(self.git(self.site, 'rev-list', '--count', 'origin/main..main'))

    def ci_commits(self, tracking, data):
        """CI's daily run: clone GitHub, write its results, commit, push (daily-check.yml)."""
        self.git(self.tmp, 'clone', '-q', self.remote, self.ci)
        for name, obj in (('movie_tracking.json', {'movies': tracking}), ('data.json', data)):
            with open(os.path.join(self.ci, name), 'w', encoding='utf-8') as f:
                json.dump(obj, f, indent=2, ensure_ascii=False)
        self.git(self.ci, 'add', 'data.json', 'movie_tracking.json')
        self.git(self.ci, 'commit', '-q', '-m', 'Daily NRW Update (model of CI commit d86def0a)')
        self.git(self.ci, 'push', '-q', 'origin', 'main')


def _admin_in_site(repos, monkeypatch, update_running=lambda: False):
    """The admin as launch_all.sh runs it: cwd = the site checkout, SITE_ROOT = it, the real
    _git_commit_push (pushing only to the throwaway GitHub). One process: one TrackingDB."""
    import admin.config as admin_config
    import pipeline.tracking_db as tdb_mod
    monkeypatch.chdir(repos.site)
    monkeypatch.setattr(tdb_mod, '_shared_instance', None)
    real_connect = socket.socket.connect

    def no_network(s, addr):
        if s.family == socket.AF_UNIX:
            return real_connect(s, addr)
        raise OSError(f'network disabled in this test: {addr}')
    monkeypatch.setattr(socket.socket, 'connect', no_network)
    client = _admin_app(monkeypatch, publish=None, update_running=update_running)
    import admin.routes.curate_flow as curate_flow
    monkeypatch.setattr(admin_config, 'SITE_ROOT', repos.site)
    monkeypatch.setattr(curate_flow, 'SITE_ROOT', repos.site)
    return client


# ===========================================================================
# EO-1: a long-running admin re-reads movie_tracking.json after a `git pull`
# ===========================================================================

def test_eo1_the_shared_tracking_db_rereads_the_file_a_git_pull_brought_in(tmp_path, monkeypatch):
    """EO-1 (unit; port of the skeptic's test_eo1_tracking_singleton, fixed behaviour). The admin
    reads tracking once (Harlem and Liberation, verbatim 78303fd6 records, both waiting). Then a
    `git pull` brings CI's day in: Harlem went on the wall, Mastermind was intaked. The admin's next
    get_tracking_db() must see that file. Without the fix the shared TrackingDB kept its old copy for
    the life of the process, and the admin's next save exported it over the pulled file."""
    from pipeline import tracking_db as tdb_mod
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(tdb_mod, '_shared_instance', None)
    harlem, lib, master = h.real(HARLEM), h.real(h.LIBERATION), h.real(h.MASTERMIND)
    with open('movie_tracking.json', 'w') as f:
        json.dump({'movies': {HARLEM: harlem, h.LIBERATION: lib}}, f)
    assert set(tdb_mod.get_tracking_db().load_all()['movies']) == {HARLEM, h.LIBERATION}

    time.sleep(0.05)
    pulled = {HARLEM: {**harlem, 'status': 'available', 'digital_date': '2026-11-15'},
              h.LIBERATION: lib, h.MASTERMIND: master}
    with open('movie_tracking.json', 'w') as f:      # what `git pull` does to the file
        json.dump({'movies': pulled}, f)

    movies = tdb_mod.get_tracking_db().load_all()['movies']
    assert movies == pulled, {k: v.get('status') for k, v in movies.items()}


def test_eo1_a_process_own_saves_never_look_like_a_pull(tmp_path, monkeypatch):
    """EO-1 (save_all stamps the DB). The admin saves tracking (an export of what it holds), then
    asks for the DB again: nothing may be re-imported (the real file has 23,573 records: a re-import
    on every call is ~1 s, and a save would look newer than a later pull). A later pull is read
    exactly once. Without the stamp, the export (written after the DB) always looked newer."""
    from pipeline import tracking_db as tdb_mod
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(tdb_mod, '_shared_instance', None)
    with open('movie_tracking.json', 'w') as f:
        json.dump({'movies': {HARLEM: h.real(HARLEM)}}, f)
    tdb = tdb_mod.get_tracking_db()
    imports = []
    real_import = tdb.import_json
    monkeypatch.setattr(tdb, 'import_json', lambda path: imports.append(path) or real_import(path))

    movies = tdb.load_all()
    movies['movies'][HARLEM]['status'] = 'available'
    assert tdb.save_all(movies)
    assert os.path.getmtime('movie_tracking.json') <= os.path.getmtime('movie_tracking.db')
    assert tdb_mod.get_tracking_db().load_all()['movies'][HARLEM]['status'] == 'available'
    assert imports == [], 'its own save was re-imported'

    time.sleep(0.05)
    with open('movie_tracking.json', 'w') as f:      # a git pull
        json.dump({'movies': {HARLEM: {**h.real(HARLEM), 'status': 'removed'}}}, f)
    for _ in range(3):
        assert tdb_mod.get_tracking_db().load_all()['movies'][HARLEM]['status'] == 'removed'
    assert imports == ['movie_tracking.json'], imports


def _day0_then_ci_then_pull(repos, monkeypatch):
    """Production's data on GitHub and in the owner's checkout; the admin (one long-running process)
    reverts film X on day 0 (publishing it); CI's real daily commit of 11-15 lands on GitHub (it
    started from GitHub, so it carries X as the owner left it); the Telegram bot syncs the checkout
    (`git pull --ff-only origin main`, nrw_telegram_bot.py). Returns the admin client and CI's files."""
    repos.create({name: _real_file(P_DATA, name)
                  for name in ('data.json', 'movie_tracking.json', 'data_archive.json')})
    p_trk = _real_json(P_DATA, 'movie_tracking.json')['movies']
    c_trk = _real_json(CI_DATA, 'movie_tracking.json')['movies']
    p_wall = {str(m['id']): m for m in _real_json(P_DATA, 'data.json')['movies']}
    c_data = _real_json(CI_DATA, 'data.json')
    c_wall = {str(m['id']): m for m in c_data['movies']}
    on_both_walls = [mid for mid in c_wall if mid in p_wall and not c_wall[mid].get('hidden')
                     and not p_wall[mid].get('hidden') and p_trk.get(mid, {}).get('status') == 'available'
                     and c_trk.get(mid, {}).get('status') == 'available']
    waiting = [mid for mid, r in p_trk.items() if mid.isdigit() and r.get('status') == 'tracking'
               and c_trk.get(mid) == r and mid not in p_wall and mid not in c_wall]
    x = on_both_walls[0]

    client = _admin_in_site(repos, monkeypatch)
    r = client.post('/revert-movie', json={'movie_id': x}).get_json()
    assert r['success'] and r['warning'] is None and 'Saved and published' in r['message'], r

    ci_trk = copy.deepcopy(c_trk)
    ci_trk[x] = repos.github_json('movie_tracking.json')['movies'][x]
    ci_data = copy.deepcopy(c_data)
    ci_data['movies'] = [m for m in ci_data['movies'] if str(m['id']) != x] + \
        [m for m in repos.github_json('data.json')['movies'] if str(m['id']) == x]
    time.sleep(0.05)
    repos.ci_commits(ci_trk, ci_data)
    assert 'Fast-forward' in repos.git(repos.site, 'pull', '--ff-only', 'origin', 'main')
    added = [k for k in c_trk if k not in p_trk]
    put_on_wall = [k for k in c_trk if k in p_trk and p_trk[k].get('status') == 'tracking'
                   and c_trk[k].get('status') == 'available']
    assert len(added) == 41 and len(put_on_wall) == 3, (len(added), put_on_wall)   # the real CI day
    return client, ci_trk, {'wall': on_both_walls[1], 'waiting': waiting[0], 'put_on_wall': put_on_wall}


@pytest.mark.parametrize('action', ['revert', 'remove', 'add', 'field_edit'])
def test_eo1_an_admin_save_after_the_daily_pull_keeps_cis_tracking_work(tmp_path, monkeypatch, action):
    """EO-1 (end to end, throwaway repos, real data). The admin has been running since day 0 (it
    reverted one film then). CI's real 11-15 commit lands (41 new tracking records, 79 changed,
    Daayra / Fume / Silent Night put on the wall) and the bot pulls it into the checkout. Day 1, the
    same admin process: Revert (publishes itself), or Remove / Add / an RT-score edit followed by the
    commit-and-push every /flow save makes (curate_flow._git_commit_push of data.json +
    movie_tracking.json). GitHub's movie_tracking.json must still hold every record CI wrote,
    unchanged except the film acted on. Without the fix it held the admin's day-0 copy: 41 records
    deleted, 79 rolled back (three films back to 'tracking' after CI put them on the wall), and the
    owner was told 'Saved and published.'"""
    repos = Repos(tmp_path, monkeypatch)
    client, ci_trk, films = _day0_then_ci_then_pull(repos, monkeypatch)
    y = films['waiting'] if action == 'add' else films['wall']

    if action == 'revert':
        r = client.post('/revert-movie', json={'movie_id': y}).get_json()
        assert r['success'] and r['warning'] is None and 'Saved and published' in r['message'], r
    else:
        if action == 'remove':
            r = client.post('/remove-movie', json={'movie_id': y}).get_json()
        elif action == 'add':
            r = client.post('/add-movie', json={'tmdb_id': y, 'title': ci_trk[y]['title']}).get_json()
        else:
            r = client.post('/update-movie-fields', json={'movie_id': y, 'rt_score': 87}).get_json()
        assert r['success'], r
        import admin.routes.curate_flow as curate_flow
        assert curate_flow._git_commit_push(['data.json', 'movie_tracking.json'], f'{action} (test)') is None

    pushed = repos.github_json('movie_tracking.json')['movies']
    lost = sorted(k for k in ci_trk if k not in pushed)
    rolled_back = sorted(k for k in ci_trk if k in pushed and k != y and pushed[k] != ci_trk[k])
    assert (len(lost), len(rolled_back)) == (0, 0), (
        f'GitHub lost {len(lost)} of CI\'s records and rolled back {len(rolled_back)}, e.g. '
        f'{[ci_trk[k].get("title") for k in (lost + rolled_back)[:4]]}')
    assert all(pushed[k]['status'] == 'available' for k in films['put_on_wall'])
    after = pushed[y]
    expected = {'revert': ('tracking', '_reverted_by_owner'), 'remove': ('removed', 'removed_from_wall'),
                'add': ('available', 'last_manual_edit'), 'field_edit': (ci_trk[y]['status'], 'manual_rt_score')}
    status, mark = expected[action]
    assert after['status'] == status and after.get(mark), after


def _remove_md_step3(mid):
    """Run .claude/commands/remove.md Step 3 -- the doc's own snippet, extracted from the file -- in
    the current checkout: it edits data.json and movie_tracking.json directly (not through the DB)."""
    with open(os.path.join(ROOT, '.claude', 'commands', 'remove.md')) as f:
        doc = f.read()
    step3 = doc[doc.index('## Step 3'):doc.index('## Step 4')]
    code = re.search(r'/usr/bin/python3 -c "\n(.*?)\n"\n```', step3, re.S).group(1)
    code = code.replace('\\"', '"').replace('REPLACE_WITH_ID', str(mid))
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        exec(compile(code, 'remove.md Step 3', 'exec'), {})
    return buf.getvalue()


def test_eo1_a_remove_made_in_a_chat_window_survives_the_admins_next_save(tmp_path, monkeypatch):
    """EO-1 side effect (rule 5: Remove is permanent). The admin is running (it reverted film A).
    In a chat window the owner runs /remove on film B: remove.md Step 3 writes movie_tracking.json
    DIRECTLY (status 'removed'), Step 4 commits and pushes. Then the owner clicks Revert on film C in
    the still-running admin. GitHub must still say B is removed. Without the re-read, the admin
    exported its own old copy (B 'available') over the file and pushed it: the Remove was undone."""
    repos = Repos(tmp_path, monkeypatch)
    files, _ = _small_site_files()
    repos.create(files)
    wall = [str(m['id']) for m in json.loads(files['data.json'])['movies']]
    a, b, c = wall[0], wall[1], wall[2]
    client = _admin_in_site(repos, monkeypatch)
    assert client.post('/revert-movie', json={'movie_id': a}).get_json()['warning'] is None

    time.sleep(0.05)
    assert 'Marked status=removed' in _remove_md_step3(b)
    repos.git(repos.site, 'add', 'data.json', 'movie_tracking.json')
    repos.git(repos.site, 'commit', '-q', '-m', f'Remove {b} from NRW wall APPROVED: DELETE')
    repos.git(repos.site, 'push', '-q', 'origin', 'main')
    assert repos.github_json('movie_tracking.json')['movies'][b]['status'] == 'removed'

    r = client.post('/revert-movie', json={'movie_id': c}).get_json()
    assert r['success'] and r['warning'] is None, r
    pushed = repos.github_json('movie_tracking.json')['movies']
    assert pushed[b]['status'] == 'removed' and pushed[b]['removed_reason'] == 'manual_removal', pushed[b]
    assert pushed[a]['_reverted_by_owner'] and pushed[c]['_reverted_by_owner']
    assert b not in {str(m['id']) for m in repos.github_json('data.json')['movies']}


# ===========================================================================
# CRIT-4: no Revert while today's GitHub update is in flight
# ===========================================================================

class _Ran:
    def __init__(self, returncode=0, stdout='', stderr=''):
        self.returncode, self.stdout, self.stderr = returncode, stdout, stderr


@pytest.mark.parametrize('gh_says, expected', [
    (_Ran(stdout='[{"status":"in_progress"}]'), True),
    (_Ran(stdout='[{"status":"queued"}]'), True),
    (_Ran(stdout='[{"status":"waiting"}]'), True),
    (_Ran(stdout='[{"status":"completed"}]'), False),
    (_Ran(stdout='[]'), False),                                        # no run yet
    (_Ran(returncode=1, stderr='gh: To get started, run: gh auth login'), None),
    (_Ran(stdout='not json'), None),
    (OSError('No such file or directory: gh'), None),                  # gh not installed
    (subprocess.TimeoutExpired(['gh'], 20), None),                     # offline / hung
])
def test_crit4_github_run_status_decides_whether_the_daily_update_is_running(tmp_path, monkeypatch, gh_says,
                                                                            expected):
    """CRIT-4: _daily_update_running asks `gh run list --workflow daily-check.yml --limit 1 --json
    status` in the site folder. Queued / running (anything but 'completed') -> True; a finished run or
    none -> False; gh failing, offline, missing or answering garbage -> None (the revert goes ahead,
    as before the check). subprocess.run is replaced: gh is never really called. Without the check a
    revert pushed mid-run could make CI's own push fail and lose that day's whole update."""
    monkeypatch.chdir(tmp_path)          # importing the admin makes a logs/ folder in the cwd
    import admin.routes.movies as movies_mod
    from admin.config import SITE_ROOT
    calls = []

    def fake_run(cmd, **kw):
        calls.append((cmd, kw))
        if isinstance(gh_says, BaseException):
            raise gh_says
        return gh_says
    monkeypatch.setattr(subprocess, 'run', fake_run)
    monkeypatch.setattr('shutil.which', lambda name: '/fake/bin/gh' if name == 'gh' else None)
    assert movies_mod._daily_update_running() is expected
    (cmd, kw), = calls
    assert cmd == ['/fake/bin/gh', 'run', 'list', '--workflow', 'daily-check.yml', '--limit', '1', '--json', 'status']
    assert kw['cwd'] == SITE_ROOT and kw['timeout'] <= 30


def _harlem_on_the_wall(world):
    """Harlem (verbatim 78303fd6 record) on the main wall since yesterday -- before any revert."""
    rec = h.real(HARLEM)
    for k in ('_jw_revert_count', '_jw_revert_reason', '_jw_reverted_at'):
        rec.pop(k)
    rec.update({'status': 'available', 'digital_date': h.day(-1), '_transitioned_at': h.day(-1),
                '_discovery_source': 'provider_availability_check'})
    world.seed({HARLEM: rec}, wall=[{'id': HARLEM, 'title': Q, 'digital_date': h.day(-1),
                                     '_enrichment_status': 'completed'}])


def test_crit4_revert_refuses_while_todays_update_runs_and_changes_nothing(world, monkeypatch):
    """CRIT-4: the owner clicks Revert on Harlem while today's GitHub update is running (gh says
    'in_progress'). Nothing may change -- tracking, data.json, no commit, no push -- and the owner is
    told to revert after it finishes. Without the refusal the revert was pushed at once; CI's final
    `git pull --rebase` then conflicted on a recent film's data.json lines (13 of 316 recent
    arrivals in the critic's replay), the merge fallback too, and the day's update never published."""
    import admin.config as admin_config
    _harlem_on_the_wall(world)
    before_trk = copy.deepcopy(world.tracking())
    with open('data.json', 'rb') as f:
        before_wall = f.read()
    published = []
    client = _admin_app(monkeypatch, clock_module=h.discoverer_mod,
                        publish=lambda files, msg: published.append(files), update_running=lambda: True)
    monkeypatch.setattr(admin_config, 'SITE_ROOT', world.tmp)        # the admin runs in the site folder

    r = client.post('/revert-movie', json={'movie_id': HARLEM}).get_json()

    assert r['success'] is False and 'running on GitHub' in r['error'] and 'Nothing was changed' in r['error'], r
    assert world.tracking() == before_trk
    with open('data.json', 'rb') as f:
        assert f.read() == before_wall
    assert published == []


@pytest.mark.parametrize('gh', [False, None], ids=['update-finished', 'gh-cannot-tell'])
def test_crit4_revert_goes_ahead_when_the_update_is_done_or_github_cannot_tell(world, monkeypatch, gh):
    """CRIT-4 (no over-blocking): gh says the latest run is completed (False), or gh can't tell
    (None: not installed, offline). The revert goes ahead and publishes both files, as in round 2d."""
    import admin.config as admin_config
    _harlem_on_the_wall(world)
    published = []
    client = _admin_app(monkeypatch, clock_module=h.discoverer_mod,
                        publish=lambda files, msg: published.append(files), update_running=lambda: gh)
    monkeypatch.setattr(admin_config, 'SITE_ROOT', world.tmp)
    r = client.post('/revert-movie', json={'movie_id': HARLEM}).get_json()
    assert r['success'] and 'Saved and published' in r['message'], r
    assert published == [['data.json', 'movie_tracking.json']]
    assert world.tracking()[HARLEM]['_reverted_by_owner'] == h.TODAY


def test_crit4_an_admin_outside_the_site_folder_never_asks_github(world, monkeypatch):
    """CRIT-4: a copy of the admin running elsewhere (a test, a worktree) never commits, so it must
    not ask GitHub either (gh stand-in fails the test if called): the revert is made locally and
    reported NOT PUBLISHED YET."""
    _harlem_on_the_wall(world)
    client = _admin_app(monkeypatch, clock_module=h.discoverer_mod)   # SITE_ROOT is the worktree, not here
    r = client.post('/revert-movie', json={'movie_id': HARLEM}).get_json()
    assert r['success'] and 'NOT PUBLISHED YET' in r['message'], r
    assert world.tracking()[HARLEM]['status'] == 'tracking'


def test_crit4_revert_command_waits_out_todays_update_before_pulling():
    """CRIT-4, CLI path (.claude/commands/revert.md Step 1): check `gh run list --workflow
    daily-check.yml` first and stop unless the status is `completed`, then pull. The workflow it
    names must be the one that pushes the day's data (else gh errors, None, and the check is
    silently a no-op)."""
    doc = _revert_md()
    step1 = doc[doc.index('## Step 1'):doc.index('## Step 2')]
    gh_at = step1.index('gh run list --workflow daily-check.yml --limit 1 --json status')
    assert gh_at < step1.index('git pull origin main')
    assert re.search(r'anything but `completed`.*stop', step1, re.S), step1
    with open(os.path.join(ROOT, '.github', 'workflows', 'daily-check.yml')) as f:
        workflow = f.read()
    assert 'git push origin main' in workflow and 'movie_tracking.json' in workflow


# ===========================================================================
# EO-3: "nothing to commit" while an earlier save is still unpushed is not "published"
# ===========================================================================

def _small_site_files():
    """A small checkout of REAL rows: the first 12 films on production's 11-14 wall whose tracking
    says 'available', plus their tracking records."""
    data = _real_json(P_DATA, 'data.json')
    trk = _real_json(P_DATA, 'movie_tracking.json')['movies']
    films = [m for m in data['movies'] if trk.get(str(m['id']), {}).get('status') == 'available'
             and not m.get('hidden')][:12]
    small = {**{k: v for k, v in data.items() if k != 'movies'}, 'count': len(films), 'movies': films}
    return ({'data.json': json.dumps(small, indent=2, ensure_ascii=False),
             'movie_tracking.json': json.dumps({'movies': {str(m['id']): trk[str(m['id'])] for m in films}},
                                               indent=2, ensure_ascii=False),
             'data_archive.json': json.dumps({'movies': []})},
            str(films[0]['id']))


def _frozen_revert_clock(monkeypatch):
    """Both clicks in the same second: the second revert writes byte-identical files."""
    class Frozen(_REAL_DATETIME):
        @classmethod
        def now(cls, tz=None):
            t = _REAL_DATETIME(2026, 11, 16, 17, 0, 0, tzinfo=timezone.utc)
            return t.astimezone(tz) if tz else t.replace(tzinfo=None)
    monkeypatch.setattr(putback, 'datetime', Frozen)


def _dirty(repos):
    """The real checkout always has local edits to tracked files (git status); git then words a
    no-op commit 'no changes added to commit' instead of 'nothing to commit'."""
    with open(os.path.join(repos.site, '.gitignore'), 'a') as f:
        f.write('\n# a local edit\n')


@pytest.mark.parametrize('tree', ['clean', 'dirty'])
def test_eo3_a_second_revert_after_a_failed_push_is_not_called_published(tmp_path, monkeypatch, tree):
    """EO-3: GitHub refuses pushes (outage, expired credentials). Click 1 commits locally and warns
    NOT PUBLISHED YET. The film is still listed on /wall, so the owner clicks Revert again within the
    same second (frozen clock: since round 2e a later click re-stamps _reverted_by_owner_at, so git
    would find a change; a no-op /flow save takes the same path): the files are already written, git
    has nothing new to commit -- and round 2d said 'Saved and published.' while GitHub never got the
    revert. Now the pending commit is pushed (refused again: warned). Clean and always-dirty tree."""
    repos = Repos(tmp_path, monkeypatch)
    files, x = _small_site_files()
    repos.create(files)
    if tree == 'dirty':
        _dirty(repos)
    repos.github_refuses_pushes()
    _frozen_revert_clock(monkeypatch)
    client = _admin_in_site(repos, monkeypatch)

    r1 = client.post('/revert-movie', json={'movie_id': x}).get_json()
    assert r1['success'] and r1['warning'] and 'NOT PUBLISHED YET' in r1['message'], r1
    tried = repos.pushes_seen()
    r2 = client.post('/revert-movie', json={'movie_id': x}).get_json()

    assert r2['success'] and r2['warning'] and 'NOT PUBLISHED YET' in r2['message'], r2
    assert 'Saved and published' not in r2['message']
    assert repos.pushes_seen() > tried, 'the second click never tried to push the pending commit'
    assert repos.unpublished_commits() == 1
    assert repos.github_json('movie_tracking.json')['movies'][x]['status'] == 'available'


@pytest.mark.parametrize('tree', ['clean', 'dirty'])
def test_eo3_the_second_revert_publishes_the_pending_commit_once_github_accepts(tmp_path, monkeypatch, tree):
    """EO-3: click 1's push is refused (warned); GitHub recovers; click 2 (same second, see above) has
    nothing new to commit but an unpushed commit: it pushes it, so 'Saved and published.' is now true
    -- GitHub has the revert and nothing is left unpublished. Round 2d returned success without
    pushing: the owner was told published while the film stayed on the live site."""
    repos = Repos(tmp_path, monkeypatch)
    files, x = _small_site_files()
    repos.create(files)
    if tree == 'dirty':
        _dirty(repos)
    repos.github_refuses_pushes()
    _frozen_revert_clock(monkeypatch)
    client = _admin_in_site(repos, monkeypatch)
    r1 = client.post('/revert-movie', json={'movie_id': x}).get_json()
    assert r1['warning'], r1
    repos.github_refuses_pushes(refuse=False)

    r2 = client.post('/revert-movie', json={'movie_id': x}).get_json()

    assert r2['success'] and r2['warning'] is None and 'Saved and published' in r2['message'], r2
    assert repos.unpublished_commits() == 0
    rec = repos.github_json('movie_tracking.json')['movies'][x]
    assert rec['status'] == 'tracking' and rec['_reverted_by_owner']
    entry = next(m for m in repos.github_json('data.json')['movies'] if str(m['id']) == x)
    assert entry['hidden'] is True and entry['_enrichment_status'] == 'reverted'


def test_eo3_nothing_new_and_nothing_pending_is_published_without_a_push(tmp_path, monkeypatch):
    """EO-3 control: a save with nothing to commit and nothing unpushed (a /flow save of unchanged
    files) still reports success, and does not contact GitHub (even one that is down)."""
    repos = Repos(tmp_path, monkeypatch)
    files, _ = _small_site_files()
    repos.create(files)
    repos.github_refuses_pushes()
    _admin_in_site(repos, monkeypatch)
    import admin.routes.curate_flow as curate_flow
    assert curate_flow._git_commit_push(['data.json', 'movie_tracking.json'], 'no-op save') is None
    assert repos.pushes_seen() == 0


# ===========================================================================
# EO-4 / REV-3: the admin's "Add movie" and a reverted film
# ===========================================================================

def test_eo4_admin_add_of_a_reverted_films_hidden_entry_is_refused_clearly_and_changes_nothing(world, monkeypatch):
    """EO-4: the owner reverts Harlem (its entry stays in data.json, hidden, until the next run),
    then tries the admin's Add form the same day. The form can't put it back; it must say why and
    where (/add-movie), and change nothing. Round 2d said 'Movie already exists on site' about a
    film the site does not show."""
    h._harlem_on_the_wall_by_mistake(world)
    assert world.wall()[HARLEM]['hidden'] is True
    before_trk = copy.deepcopy(world.tracking())
    with open('data.json', 'rb') as f:
        before_wall = f.read()
    client = _admin_app(monkeypatch, clock_module=h.discoverer_mod)

    r = client.post('/add-movie', json={'tmdb_id': HARLEM, 'title': Q}).get_json()

    assert r['success'] is False and 'reverted' in r['error'] and '/add-movie' in r['error'], r
    assert world.tracking() == before_trk
    with open('data.json', 'rb') as f:
        assert f.read() == before_wall


def _readd_with_the_admin_form(world, monkeypatch):
    """Harlem reverted on day 0 (the pre-order problem); day 1's run purges its entry; day 2 the
    owner re-adds it with the admin's Add form (existing tracking record)."""
    h._harlem_on_the_wall_by_mistake(world)
    world.pages.text = INCONCLUSIVE
    world.run(on_day=1)
    world.enrich(on_day=1)
    assert HARLEM not in world.wall() and world.tracking()[HARLEM]['status'] == 'tracking'
    client = _admin_app(monkeypatch, clock_module=h.discoverer_mod)
    world.clock.days = 2
    r = client.post('/add-movie', json={'tmdb_id': HARLEM, 'title': Q, 'digital_date': h.day(2)}).get_json()
    assert r['success'], r
    return client


def test_rev3_admin_readd_clears_the_owners_revert_but_keeps_the_not_out_yet_day(world, monkeypatch):
    """REV-3 / EO-4 (port of test_rev3a, fixed behaviour): after the admin re-add, tracking is
    'available' with none of the owner-revert keys, so no later hold can turn it back into "the
    owner's revert"; its last "not out yet" day stays (rule 3: it is permanent). Round 2d kept
    _reverted_by_owner (only scripts/add_movie.py cleared it)."""
    _readd_with_the_admin_form(world, monkeypatch)
    rec = world.tracking()[HARLEM]
    assert rec['status'] == 'available' and rec['digital_date'] == h.day(2)
    assert [k for k in REVERT_KEYS if k in rec] == [], rec
    assert rec['_jw_last_refuted'] == h.TODAY
    assert not putback.is_owner_reverted({**rec, 'status': 'tracking'})
    assert _site_shows(world.wall()[HARLEM])


def test_rev3_after_an_admin_readd_a_buy_only_hold_is_an_ordinary_preorder_and_it_comes_back(world, monkeypatch):
    """REV-3 (port of test_rev3b / the reviewer's DEFECT test, fixed behaviour). After the admin
    re-add (day 2), the gap fill sees JustWatch list Harlem for purchase only (SYNTHETIC buy offers,
    store page unreadable) and flags it a buy-only pre-order (tracking back to 'tracking'). That is an
    ordinary buy-only pre-order now, not the owner's revert: day 3's enrichment keeps it in the
    PRE-ORDER lane, the morning report does not call it "sent back", and on day 4 -- a rental listed,
    the store page reading "available" -- it is back on the main wall, dated day 4. Round 2d: the
    stale _reverted_by_owner made it the owner's revert again -- purged off the wall, judged by the
    revert gate from the OLD revert day, still waiting on day 4: the re-add silently undone."""
    _readd_with_the_admin_form(world, monkeypatch)
    node = world.jw.node(Q, HARLEM)
    node['offers'] = _cinema(node) + [
        h.jw_offer('BUY', 'Amazon Video', h.HARLEM_AMAZON, '$19.99', f'{h.day(-5)}T07:00:00Z', created=h.day(-5)),
        h.jw_offer('BUY', 'Apple TV Store', HARLEM_APPLE, '$19.99', '2026-10-16T07:00:00Z', created=h.day(-5))]
    # Round 2f+: a purchase is out unless there's positive pre-order evidence (owner, Nov 2026)
    # -- here Amazon's page still reads "Pre-order", so it is an ordinary pre-order hold.
    world.pages.text = h.FakeStorePages.AMAZON_PREORDER
    world._phase(lambda: world.gen.daily_gap_fill(), 'gap fill', 2)
    rec = world.tracking()[HARLEM]
    assert rec['status'] == 'tracking' and rec.get('_buyonly_preorder'), rec
    assert not putback.is_owner_reverted(rec)
    assert world.wall()[HARLEM].get('_is_preorder')

    world.enrich(on_day=3)
    entry = world.wall().get(HARLEM)
    assert entry and entry.get('_is_preorder') and not entry.get('hidden'), entry   # still in the pre-order lane
    world.run(on_day=3)
    assert 'you sent it back' not in world.morning_report(h.day(3))

    node['offers'].append(h.jw_offer('RENT', 'Apple TV Store', HARLEM_APPLE, '$5.99', '2026-10-16T07:00:00Z',
                                     created=h.day(-5)))
    world.pages.text = h.FakeStorePages.AVAILABLE
    world.run(on_day=4)
    r4 = world.tracking()[HARLEM]
    assert 'reverted by the owner on' not in world.last_output
    assert r4['status'] == 'available' and r4['digital_date'] == h.day(4), r4


# ===========================================================================
# EO-2: /add-movie puts a reverted film back the same day
# ===========================================================================

def _beware_out_and_on_the_wall(nrw):
    """Beware Boiuna (verbatim 78303fd6 rows) as a film that is out: tracking 'available', a visible
    main-wall entry with its real watch links (pre-order flags dropped)."""
    mid = BEWARE
    nrw.seed(mid, **{mid: {'status': 'available', '_buyonly_preorder': None, '_is_preorder': None,
                           '_transitioned_at': None, 'digital_date': '2026-11-03'}})
    entry = copy.deepcopy(e.WALL_78303FD6[mid])
    for k in ('_is_preorder', '_buyonly_preorder', 'pre_order_links'):
        entry.pop(k, None)
    nrw.put_on_wall(entry)
    assert nrw.lane(mid) == 'MAIN WALL'
    return mid


def _script(nrw, name, *argv):
    mod = nrw.script(name)
    nrw.mp.setattr(sys, 'argv', [f'{name}.py', *argv])
    return nrw.printed(mod.main)


def test_eo2_add_movie_duplicate_check_calls_a_reverted_entry_safe_to_add(nrw):
    """EO-2 (.claude/commands/add-movie.md Step 3, the doc's own snippet): a visible wall entry is
    ALREADY ON WALL (stop); once the owner reverts it, the hidden entry is REVERTED/HIDDEN -- safe to
    add (this puts it back). Round 2d printed ALREADY ON WALL for the hidden entry and the doc said
    stop: the documented way back stopped with a wrong message."""
    mid = _beware_out_and_on_the_wall(nrw)
    assert _add_movie_md_duplicate_check(mid).startswith('ALREADY ON WALL')
    _script(nrw, 'revert_movie', mid)
    assert nrw.lane(mid) == 'HIDDEN'
    said = _add_movie_md_duplicate_check(mid)
    assert said.startswith('REVERTED/HIDDEN') and 'safe to add' in said, said


def test_eo2_same_day_add_movie_after_a_revert_puts_the_film_back_on_the_main_wall(nrw):
    """EO-2 (port of the skeptic's test_fix_same_day_readd_shows_it, on the real 2e add_movie.py).
    The owner reverts Beware Boiuna with scripts/revert_movie.py, changes their mind the same day and
    runs /add-movie: add_movie.py, then --enrich-id. The entry loses the revert's hide (and any
    JustWatch-wait hide), tracking loses every owner-revert key (incl. _reverted_by_owner_at and
    _revert_page_preorder) but keeps its last "not out yet" day, and the film is on the main wall --
    still there after the next day's discovery, enrichment and purge. Round 2d left it hidden
    (nothing lifts a revert's hide) on every device until it aged off, 90 days."""
    mid = _beware_out_and_on_the_wall(nrw)
    _script(nrw, 'revert_movie', mid)
    assert nrw.lane(mid) == 'HIDDEN' and nrw.track(mid)['_reverted_by_owner'] == e.today()

    out = _script(nrw, 'add_movie', mid)
    assert 'Done!' in out and 'Cleared hidden' in out, out
    entry, rec = nrw.wall()[mid], nrw.track(mid)
    assert 'hidden' not in entry and '_jw_unconfirmed' not in entry and entry.get('_enrichment_status') != 'reverted'
    assert rec['status'] == 'available' and [k for k in REVERT_KEYS if k in rec] == [], rec
    assert rec['_jw_last_refuted'] == e.today()

    nrw.new_generator().enrich_newly_available_movies(target_id=mid)          # Step 5: --enrich-id
    assert nrw.lane(mid) == 'MAIN WALL' and _site_shows(nrw.wall()[mid]), nrw.wall()[mid]

    nrw.next_day(1)
    nrw.nothing_new_today(e.day(1))
    nrw.discover()
    nrw.enrich()                                                            # ends with the purge
    assert nrw.lane(mid) == 'MAIN WALL' and _site_shows(nrw.wall()[mid])
    assert nrw.track(mid)['status'] == 'available'


def test_eo2_add_movie_after_the_purge_still_puts_the_film_back(nrw):
    """EO-2 control (port of test_control_readd_after_the_purge_is_visible): reverted, purged by the
    next run, THEN /add-movie: the duplicate check says IN TRACKING, a new entry is added, and after
    --enrich-id the film is on the main wall."""
    mid = _beware_out_and_on_the_wall(nrw)
    _script(nrw, 'revert_movie', mid)
    nrw.next_day(1)
    nrw.nothing_new_today(e.day(1))
    nrw.discover()
    nrw.enrich()
    assert mid not in nrw.wall()
    assert _add_movie_md_duplicate_check(mid).startswith('IN TRACKING')
    out = _script(nrw, 'add_movie', mid)
    assert 'New entry added to data.json' in out
    nrw.new_generator().enrich_newly_available_movies(target_id=mid)
    assert nrw.lane(mid) == 'MAIN WALL' and _site_shows(nrw.wall()[mid])


def test_eo4_admin_readd_then_a_buy_only_flag_keeps_beware_in_the_preorder_lane(nrw):
    """EO-4 (port of the skeptic's test_fix_admin_readd_drops_revert_marks, on the real 2e route,
    no stand-in). Admin Revert of Beware Boiuna; the same-day admin Add is refused with the clear
    reverted message; the next day's run purges the entry; the admin Add then succeeds and clears
    the owner-revert marks; JustWatch lists it buy-only (its real Amazon / Apple $14.99 buys), so the
    gap fill flags it a buy-only pre-order. It must stay on the wall in the PRE-ORDER lane, checked
    daily. Round 2d: the stale _reverted_by_owner made the next purge archive it -- off the wall."""
    mid = _beware_out_and_on_the_wall(nrw)
    client = _admin_app(nrw.mp)
    r = client.post('/revert-movie', json={'movie_id': mid}).get_json()
    assert r['success'] and nrw.lane(mid) == 'HIDDEN', r
    r = client.post('/add-movie', json={'tmdb_id': mid, 'title': 'Beware Boiúna'}).get_json()
    assert r['success'] is False and 'reverted' in r['error'] and '/add-movie' in r['error'], r

    nrw.next_day(1)
    nrw.nothing_new_today(e.day(1))
    nrw.discover()
    nrw.enrich()
    assert mid not in nrw.wall()
    r = client.post('/add-movie', json={'tmdb_id': mid, 'title': 'Beware Boiúna'}).get_json()
    assert r['success'] and nrw.lane(mid) == 'MAIN WALL', r
    assert [k for k in REVERT_KEYS if k in nrw.track(mid)] == [], nrw.track(mid)

    nrw.jw.catalog['Beware Boiúna'] = [e.synthetic_node(
        mid, 'Beware Boiúna', 2026, 'beware-boiuna',
        offers=[e._offer('BUY', 'Amazon Video', 'amazon',
                         'https://watch.amazon.com/detail?gti=amzn1.dv.gti.a9eb0d4b-efba-4225-a259-caaa18dda9fb',
                         price='$14.99'),
                e._offer('BUY', 'Apple TV', 'itunes',
                         'https://tv.apple.com/us/movie/beware-boiuna/umc.cmc.63lzx7ql8ok0fkbe57jjsjqqt',
                         price='$14.99')],
        director='Mike P. Nelson')]
    # Round 2f+: a purchase is out unless there's positive pre-order evidence (owner, Nov 2026)
    # -- here Amazon's page still reads "Pre-order", so the gap fill flags an ordinary pre-order.
    nrw.page_verdict = 'pre-order'
    nrw.next_day(2)
    nrw.nothing_new_today(e.day(2))
    nrw.new_generator().daily_gap_fill()
    rec = nrw.track(mid)
    assert rec['status'] == 'tracking' and not putback.is_owner_reverted(rec), rec
    nrw.discover()
    nrw.enrich()                                   # ends with the purge
    assert nrw.lane(mid) == 'PRE-ORDER', nrw.lane(mid)
    rec = nrw.track(mid)
    assert rec['status'] == 'tracking' and rec.get('_buyonly_preorder') and not putback.is_owner_reverted(rec), rec
