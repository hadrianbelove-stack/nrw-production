#!/usr/bin/env python3
"""NRW Telegram Bot — Remote control for the movie pipeline from your phone."""

import os
import sys
import json
import re
import logging
import logging.handlers
import asyncio
from datetime import datetime, timedelta
from pathlib import Path
from functools import wraps

# Load environment variables using existing project mechanism
sys.path.insert(0, str(Path(__file__).parent))
import load_env

from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

# === Configuration ===
PROJECT_DIR = Path(__file__).parent
BOT_TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN')
OWNER_ID = int(os.environ.get('TELEGRAM_OWNER_ID', '0'))
ADMIN_URL = 'http://localhost:5556'

# === Logging ===
log_dir = PROJECT_DIR / 'logs'
log_dir.mkdir(exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.handlers.RotatingFileHandler(
            log_dir / 'telegram_bot.log',
            maxBytes=5 * 1024 * 1024,
            backupCount=3
        )
    ]
)
logger = logging.getLogger(__name__)


# === Security ===
def owner_only(func):
    """Only allow the configured owner to use commands."""
    @wraps(func)
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
        if update.effective_user.id != OWNER_ID:
            await update.message.reply_text("Not authorized.")
            logger.warning(f"Unauthorized access attempt from user {update.effective_user.id}")
            return
        return await func(update, context)
    return wrapper


# === Helper Functions ===
def read_json(path):
    """Read a JSON file, return None if missing or invalid."""
    try:
        with open(PROJECT_DIR / path) as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError) as e:
        logger.error(f"Failed to read {path}: {e}")
        return None


def fmt_duration(seconds):
    """Format seconds into a human-readable string."""
    if seconds > 120:
        return f"{seconds / 60:.1f} min"
    return f"{seconds:.0f}s"


def fmt_number(n):
    """Format a number with commas."""
    try:
        return f"{int(n):,}"
    except (TypeError, ValueError):
        return str(n)


# === Command Handlers ===

@owner_only
async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show available commands."""
    await update.message.reply_text(
        "NRW Pipeline Bot\n\n"
        "/status \u2014 Pipeline health & last run\n"
        "/add <tmdb_id> \u2014 Add movie to tracking\n"
        "/latest \u2014 Today's new arrivals\n"
        "/counts \u2014 Data quality numbers\n"
        "/pipeline \u2014 Trigger full pipeline (~60 min)\n"
        "/help \u2014 This message"
    )


@owner_only
async def cmd_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show pipeline health summary from run_diagnostics.json."""
    diag = read_json('metrics/run_diagnostics.json')
    if not diag:
        await update.message.reply_text("No diagnostics found \u2014 has the pipeline run yet?")
        return

    ts = datetime.fromisoformat(diag['timestamp'])
    age_hours = (datetime.now() - ts).total_seconds() / 3600

    # Status indicator
    failures = diag.get('failure_count', 0)
    warnings = diag.get('warning_count', 0)
    if failures > 0:
        status_line = f"Result: {failures} failure(s)"
    elif warnings > 0:
        status_line = f"Result: {warnings} warning(s)"
    else:
        status_line = "Result: All clear"

    # Phase summary
    phases_lines = []
    for phase in diag.get('phases', []):
        icon = "\u2705" if phase['success'] else "\u274c"
        name = phase['name'][:40]
        dur = fmt_duration(phase['duration_seconds'])
        phases_lines.append(f"  {icon} {name}: {dur}")

    phases_text = "\n".join(phases_lines)

    # Data quality
    dq = diag.get('data_quality', {})

    # Stall info
    stall = diag.get('stall_status', {})
    if stall.get('stalled'):
        stall_text = f"STALLED ({stall.get('days', '?')} days)"
    else:
        stall_text = "No stall"

    msg = (
        f"Pipeline Status\n\n"
        f"Last run: {ts.strftime('%b %d, %I:%M %p')} ({age_hours:.1f}h ago)\n"
        f"Duration: {fmt_duration(diag.get('duration_seconds', 0))}\n"
        f"{status_line}\n\n"
        f"Phases:\n{phases_text}\n\n"
        f"Site: {dq.get('data_movies', '?')} movies\n"
        f"Tracking: {fmt_number(dq.get('tracking', '?'))}\n"
        f"Stall: {stall_text}"
    )

    # Append any health issues
    issues = diag.get('health_issues', [])
    if issues:
        issue_lines = [f"  - {i.get('message', '?')}" for i in issues[:5]]
        msg += "\n\nIssues:\n" + "\n".join(issue_lines)

    await update.message.reply_text(msg)


@owner_only
async def cmd_add(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Add a movie to tracking by TMDB ID (calls admin API)."""
    if not context.args:
        await update.message.reply_text("Usage: /add <tmdb_id>\nExample: /add 550")
        return

    tmdb_id = context.args[0]
    if not tmdb_id.isdigit():
        await update.message.reply_text("TMDB ID must be a number.")
        return

    try:
        import requests
        resp = requests.post(
            f'{ADMIN_URL}/add-movie',
            json={'tmdb_id': tmdb_id},
            timeout=15
        )
        result = resp.json()

        if result.get('success'):
            await update.message.reply_text(f"Added: {result.get('message', tmdb_id)}")
        else:
            await update.message.reply_text(f"Failed: {result.get('error', 'Unknown error')}")

    except Exception as e:
        error_name = type(e).__name__
        if 'ConnectionError' in error_name or 'ConnectError' in error_name:
            await update.message.reply_text(
                "Admin server not running.\n"
                "Start it on your laptop with ./launch_all.sh"
            )
        else:
            await update.message.reply_text(f"Error: {e}")


@owner_only
async def cmd_latest(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show today's new arrivals from data.json."""
    data = read_json('data.json')
    if not data:
        await update.message.reply_text("Could not read data.json.")
        return

    today = datetime.now().strftime('%Y-%m-%d')
    yesterday = (datetime.now() - timedelta(days=1)).strftime('%Y-%m-%d')

    arrivals = [m for m in data.get('movies', []) if m.get('digital_date') == today]
    date_label = "Today"

    if not arrivals:
        arrivals = [m for m in data.get('movies', []) if m.get('digital_date') == yesterday]
        date_label = "Yesterday"

    if not arrivals:
        await update.message.reply_text("No new arrivals in the last 2 days.")
        return

    lines = [f"New Arrivals ({date_label}, {len(arrivals)} movies):\n"]
    for m in arrivals[:15]:
        title = m.get('title', 'Unknown')
        providers = m.get('providers', {})
        streaming = providers.get('streaming', [])
        if streaming:
            where = streaming[0] if isinstance(streaming[0], str) else str(streaming[0])
        else:
            where = "VOD"
        lines.append(f"  {title} \u2014 {where}")

    if len(arrivals) > 15:
        lines.append(f"\n  ...and {len(arrivals) - 15} more")

    await update.message.reply_text("\n".join(lines))


@owner_only
async def cmd_counts(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show data quality numbers from run_diagnostics.json."""
    diag = read_json('metrics/run_diagnostics.json')
    if not diag:
        await update.message.reply_text("No diagnostics found.")
        return

    dq = diag.get('data_quality', {})
    enrich = diag.get('enrichment_metrics', {})

    enrich_dur = enrich.get('enrichment_duration_seconds', 0)
    enrich_dur_str = fmt_duration(enrich_dur) if enrich_dur else "N/A"

    msg = (
        f"Data Quality Counts\n\n"
        f"Total in DB: {fmt_number(dq.get('total', '?'))}\n"
        f"Tracking: {fmt_number(dq.get('tracking', '?'))}\n"
        f"Available: {fmt_number(dq.get('available', '?'))}\n"
        f"On site: {dq.get('data_movies', '?')}\n\n"
        f"Coverage:\n"
        f"  Watch links: {dq.get('movies_with_links', '?')}\n"
        f"  RT scores: {dq.get('movies_with_rt', '?')}\n"
        f"  Wikipedia: {dq.get('movies_with_wikipedia', '?')}\n"
        f"  Trailers: {dq.get('movies_with_trailers', '?')}\n\n"
        f"Last enrichment: {enrich.get('movies_enriched', '?')} movies in {enrich_dur_str}"
    )
    await update.message.reply_text(msg)


@owner_only
async def cmd_pipeline(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Trigger the full daily pipeline (with confirmation)."""
    if not context.args or context.args[0] != 'confirm':
        await update.message.reply_text(
            "This runs the full daily pipeline (~60 min).\n"
            "Send /pipeline confirm to proceed."
        )
        return

    # Check for lock file (orchestrator's own mechanism)
    lock_path = PROJECT_DIR / '.nrw_orchestrator.lock'
    if lock_path.exists():
        try:
            with open(lock_path) as f:
                lock_info = json.load(f)
            pid = lock_info.get('pid')
            try:
                os.kill(pid, 0)
                await update.message.reply_text(
                    f"Pipeline already running (PID {pid}).\n"
                    f"Started: {lock_info.get('started_at', 'unknown')}"
                )
                return
            except (OSError, TypeError):
                pass  # Stale lock, proceed
        except (json.JSONDecodeError, IOError):
            pass  # Corrupted lock, proceed

    await update.message.reply_text(
        "Pipeline started. This takes ~60 minutes.\n"
        "I'll message you when it finishes."
    )

    asyncio.create_task(
        _run_pipeline_and_notify(update.effective_chat.id, context)
    )


async def _run_pipeline_and_notify(chat_id, context):
    """Run pipeline as subprocess and send result notification."""
    try:
        proc = await asyncio.create_subprocess_exec(
            '/usr/bin/python3', 'daily_orchestrator.py',
            cwd=str(PROJECT_DIR),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        stdout, stderr = await proc.communicate()

        diag = read_json('metrics/run_diagnostics.json')
        if diag:
            dur = diag.get('duration_seconds', 0)
            failures = diag.get('failure_count', 0)
            dq = diag.get('data_quality', {})

            if failures > 0:
                status = f"Completed with {failures} failure(s)"
            else:
                status = "Completed successfully"

            msg = (
                f"Pipeline finished!\n\n"
                f"Result: {status}\n"
                f"Duration: {fmt_duration(dur)}\n"
                f"Movies on site: {dq.get('data_movies', '?')}\n"
                f"Tracking: {fmt_number(dq.get('tracking', '?'))}"
            )
        else:
            msg = f"Pipeline finished (exit code {proc.returncode})"

        await context.bot.send_message(chat_id=chat_id, text=msg)

    except Exception as e:
        logger.error(f"Pipeline execution error: {e}")
        await context.bot.send_message(
            chat_id=chat_id,
            text=f"Pipeline error: {e}"
        )


# === Proactive Notifications ===

async def check_for_new_commits(context: ContextTypes.DEFAULT_TYPE):
    """Periodic job: check if GitHub Actions pushed new daily update commits."""
    state_file = PROJECT_DIR / '.telegram_bot_state.json'

    # Load last known commit
    last_sha = None
    if state_file.exists():
        try:
            with open(state_file) as f:
                state = json.load(f)
                last_sha = state.get('last_commit_sha')
        except (json.JSONDecodeError, IOError):
            pass

    try:
        # Fetch latest from remote
        proc = await asyncio.create_subprocess_exec(
            'git', 'fetch', 'origin', 'main', '--quiet',
            cwd=str(PROJECT_DIR),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        await proc.communicate()

        # Get latest commit on origin/main
        proc = await asyncio.create_subprocess_exec(
            'git', 'log', 'origin/main', '-1', '--format=%H %s',
            cwd=str(PROJECT_DIR),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        stdout, _ = await proc.communicate()
        line = stdout.decode().strip()

        if not line:
            return

        parts = line.split(' ', 1)
        if len(parts) != 2:
            return
        sha, subject = parts

        # Save current SHA
        with open(state_file, 'w') as f:
            json.dump({
                'last_commit_sha': sha,
                'checked_at': datetime.now().isoformat()
            }, f)

        # First run: just record SHA, don't notify
        if last_sha is None:
            logger.info(f"First run \u2014 recorded commit {sha[:8]}")
            return

        # No change
        if sha == last_sha:
            return

        # Check if it's a daily update commit
        if subject.startswith('Daily NRW Update'):
            logger.info(f"New daily update detected: {sha[:8]} \u2014 {subject}")

            # Pull to sync local data files
            proc = await asyncio.create_subprocess_exec(
                'git', 'pull', '--ff-only', 'origin', 'main',
                cwd=str(PROJECT_DIR),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            await proc.communicate()

            # Extract new_arrivals count from commit message
            match = re.search(r'new_arrivals=(\d+)', subject)
            count = match.group(1) if match else '?'

            # Read fresh diagnostics
            diag = read_json('metrics/run_diagnostics.json')
            extra = ""
            if diag:
                dq = diag.get('data_quality', {})
                failures = diag.get('failure_count', 0)
                if failures > 0:
                    extra += f"\nWarnings: {failures} failure(s) in pipeline"
                extra += f"\nSite total: {dq.get('data_movies', '?')} movies"

            msg = f"Daily pipeline complete!\n\nNew arrivals: {count}{extra}"
            await context.bot.send_message(chat_id=OWNER_ID, text=msg)
        else:
            logger.info(f"New commit (not daily update): {sha[:8]} \u2014 {subject}")

    except Exception as e:
        logger.error(f"Commit check error: {e}")


# === Main ===

def main():
    """Start the NRW Telegram Bot."""
    if not BOT_TOKEN:
        print("ERROR: TELEGRAM_BOT_TOKEN not set in .env")
        print("Create a bot via @BotFather on Telegram and add the token to .env")
        sys.exit(1)
    if not OWNER_ID:
        print("ERROR: TELEGRAM_OWNER_ID not set in .env")
        print("Message @userinfobot on Telegram to get your user ID, then add to .env")
        sys.exit(1)

    app = Application.builder().token(BOT_TOKEN).build()

    # Register command handlers
    app.add_handler(CommandHandler("start", cmd_help))
    app.add_handler(CommandHandler("help", cmd_help))
    app.add_handler(CommandHandler("status", cmd_status))
    app.add_handler(CommandHandler("add", cmd_add))
    app.add_handler(CommandHandler("latest", cmd_latest))
    app.add_handler(CommandHandler("counts", cmd_counts))
    app.add_handler(CommandHandler("pipeline", cmd_pipeline))

    # Proactive: check for new CI commits every 15 minutes
    app.job_queue.run_repeating(
        check_for_new_commits,
        interval=900,
        first=60
    )

    logger.info(f"NRW Telegram Bot starting (owner_id={OWNER_ID})...")
    app.run_polling(drop_pending_updates=True)


if __name__ == '__main__':
    main()
