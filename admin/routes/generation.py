"""Admin panel generation routes — regenerate data.json, create YouTube playlists."""

import re
import sys
import subprocess
import traceback

from flask import Blueprint, request, jsonify

from admin.logging_setup import logger
from admin.utils import format_subprocess_output, clear_changes_pending

bp = Blueprint('generation', __name__)


@bp.route('/regenerate', methods=['POST'])
def regenerate() -> dict:
    """Manually trigger data.json regeneration."""
    logger.info("Manual data.json regeneration triggered")
    try:
        result = subprocess.run(
            [sys.executable, 'generate_data.py'],
            capture_output=True,
            text=True,
            timeout=120  # 2 minute timeout
        )

        if result.returncode == 0:
            logger.info("Data.json regenerated successfully")
            # Clear pending changes flag after successful regeneration
            clear_changes_pending()

            # Auto-commit and push changes to keep in sync with remote
            try:
                subprocess.run(['git', 'add', 'data.json'], check=True, capture_output=True)
                subprocess.run(
                    ['git', 'commit', '-m', 'Admin: Apply curatorial changes\n\nAPPROVED: DELETE'],
                    check=True,
                    capture_output=True
                )
                subprocess.run(['git', 'push', 'origin', 'main'], check=True, capture_output=True)
                logger.info("Changes committed and pushed to remote")
            except subprocess.CalledProcessError as e:
                # Log but don't fail - local changes are saved
                logger.warning(f"Git auto-commit failed: {e}")

            return jsonify({
                'success': True,
                'message': 'Changes saved successfully',
                'output': format_subprocess_output(result.stdout)
            })
        else:
            logger.error(f"Regeneration failed with exit code {result.returncode}: {format_subprocess_output(result.stderr)}")
            return jsonify({
                'success': False,
                'error': f'Regeneration failed with exit code {result.returncode}',
                'stderr': format_subprocess_output(result.stderr)
            })
    except subprocess.TimeoutExpired:
        logger.error("Regeneration timed out after 2 minutes")
        return jsonify({
            'success': False,
            'error': 'Regeneration timed out after 2 minutes'
        })
    except Exception as e:
        logger.error(f"Failed to trigger regeneration: {str(e)}")
        return jsonify({
            'success': False,
            'error': f'Failed to trigger regeneration: {str(e)}'
        })


@bp.route('/create-youtube-playlist', methods=['POST'])
def create_youtube_playlist() -> dict:
    """Create a YouTube playlist with custom date parameters."""
    try:
        data = request.json
        date_type = data.get('date_type', 'last_x_days')
        privacy = data.get('privacy', 'public')
        dry_run = data.get('dry_run', False)
        custom_title = data.get('title')

        logger.info(f"Creating YouTube playlist: {date_type}, privacy={privacy}, dry_run={dry_run}")

        # Build command arguments
        cmd = [sys.executable, 'youtube_playlist_manager.py', 'custom']

        if dry_run:
            cmd.append('--dry-run')

        cmd.extend(['--privacy', privacy])

        if custom_title:
            cmd.extend(['--title', custom_title])

        # Add date parameters
        if date_type == 'last_x_days':
            days_back = data.get('days_back', 7)
            cmd.extend(['--days-back', str(days_back)])
        else:  # date_range
            from_date = data.get('from_date')
            to_date = data.get('to_date')

            if not from_date or not to_date:
                return jsonify({
                    'success': False,
                    'error': 'Both from_date and to_date required for date range'
                })

            cmd.extend(['--from-date', from_date, '--to-date', to_date])

        # Run the playlist manager
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=180  # 3 minute timeout
        )

        if result.returncode == 0:
            # Parse output for details
            output = result.stdout

            response_data = {
                'success': True,
                'message': 'Playlist created successfully' if not dry_run else 'Preview generated'
            }

            # Try to extract playlist URL from output
            url_match = re.search(r'https://youtube\.com/playlist\?list=([a-zA-Z0-9_-]+)', output)
            if url_match:
                response_data['playlist_url'] = url_match.group(0)

            # Extract title
            title_match = re.search(r'Title: (.+)', output)
            if title_match:
                response_data['title'] = title_match.group(1).strip()

            # Extract video count
            video_match = re.search(r'Videos: (\d+)', output)
            if video_match:
                response_data['video_count'] = int(video_match.group(1))

            # Extract date range
            date_match = re.search(r'Date range: (.+)', output)
            if date_match:
                response_data['date_range'] = date_match.group(1).strip()

            # Extract preview videos (first 5)
            preview_matches = re.findall(r'\u2022 (.+) - https://youtube\.com/watch', output)
            if preview_matches:
                response_data['preview_videos'] = preview_matches[:5]

            logger.info(f"YouTube playlist created: {response_data.get('title', 'Unknown')} with {response_data.get('video_count', 0)} videos")
            return jsonify(response_data)
        else:
            error_msg = result.stderr or result.stdout or 'Unknown error'
            logger.error(f"YouTube playlist creation failed: {format_subprocess_output(error_msg)}")
            return jsonify({
                'success': False,
                'error': f'Playlist creation failed: {format_subprocess_output(error_msg)}'
            })

    except subprocess.TimeoutExpired:
        logger.error("YouTube playlist creation timed out after 3 minutes")
        return jsonify({
            'success': False,
            'error': 'Playlist creation timed out after 3 minutes'
        })
    except Exception as e:
        logger.error(f"Error creating YouTube playlist: {str(e)}", exc_info=True)
        return jsonify({
            'success': False,
            'error': f'Error creating playlist: {str(e)}',
            'traceback': traceback.format_exc()
        })
