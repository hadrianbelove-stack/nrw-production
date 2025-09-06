# The New Release Wall - Project Context

## Vision
The "blockbuster wall for the streaming age" - solving the broken UX of finding/renting new movies across platforms.

## Current State
- **Repo:** local only (~/Downloads/new-release-wall)
- **Last successful run:** [UPDATE ME EACH SESSION]
- **Days window:** 14
- **Stores:** Netflix, Amazon Prime Video, Apple TV, YouTube, Max, MUBI, Criterion Channel, Disney Plus, Hulu
- **Flags:** --digital (on), --only-current-year (off), --max-pages 30

## Quick Commands
\`\`\`bash
# Activate and run
cd ~/Downloads/new-release-wall
source .venv/bin/activate
python -u new_release_wall.py --region US --days 14 --stores "Netflix,Amazon Prime Video,Apple TV,YouTube,Max,MUBI,Criterion Channel,Disney Plus,Hulu" --digital --max-pages 30

# View output
open -a "Safari" output/site/index.html
\`\`\`

## Recent Changes
- [UPDATE ME]

## Open Issues
- JSON export code is unreachable (after print statement)
- Need to consolidate TMDB auth (uses both API key and bearer token)

## Next Goals
1. Fix code structure issues
2. Add director/runtime to cards
3. Deploy to Netlify/Vercel
4. Create "Tonight Mode" filter

## For AI Assistant
When working with me:
- Give exact file paths and code blocks (from → to)
- Provide complete commands in single fenced blocks
- Pick sensible defaults, don't ask for confirmation
- Keep it factual and instructional, no fluff
