# Newsletter Workflow

Generate and preview newsletter content from recent movie releases using `generate_newsletter.py`.

## Overview

The newsletter generator fetches recent movies from the NRW database and renders them into HTML and Markdown formats using Jinja2 templates. It supports a preview mode for reviewing content before final generation.

## Quick Start Commands

```bash
# Preview newsletter content (no files generated)
python3 generate_newsletter.py --preview

# Preview with custom date range
python3 generate_newsletter.py --preview --days 7

# Generate newsletter with default 7-day lookback
python3 generate_newsletter.py

# Generate with custom date range
python3 generate_newsletter.py --days 14

# Enable debug logging
python3 generate_newsletter.py --debug
```

## Command Line Options

| Flag | Description |
|------|-------------|
| `--preview` | Show summary stats without rendering templates |
| `--days N` | Number of days to look back (default: 7) |
| `--debug` | Enable debug logging output |

## Weekly Workflow Steps

### 1. Preview Content

Start by previewing what will be included:

```bash
python3 generate_newsletter.py --preview --days 7
```

This displays:
- Total movie count
- Date range covered
- RT score distribution (fresh/rotten/no score)
- Platform breakdown
- Top-rated titles

### 2. Review and Curate

Based on the preview:
- Use the admin panel to curate any pending movies
- Ensure RT scores are enriched for key titles
- Verify platform availability is accurate

### 3. Generate Newsletter

Once content is finalized:

```bash
python3 generate_newsletter.py --days 7
```

Output files are written to:
- `output/newsletter.html` - HTML version for email/web
- `output/newsletter.md` - Markdown version for archives

### 4. Review Output

Open the generated files to verify:
- Movie ordering and grouping
- Image/poster availability
- Link accuracy
- Overall formatting

## Curation Tips

### Selecting the Right Date Range

- **Weekly newsletter**: Use `--days 7` (default)
- **Bi-weekly roundup**: Use `--days 14`
- **Monthly digest**: Use `--days 30`

### Preview Best Practices

- Always run `--preview` before generating final output
- Check the RT score distribution for quality balance
- Verify platform breakdown matches expected sources
- Review top-rated titles for any surprises or errors

### Quality Checks

Before publishing:
- Confirm movie count matches expectations
- Ensure no duplicate entries
- Verify all titles have proper metadata
- Check that links and images render correctly

## Related Files

| File | Purpose |
|------|---------|
| `generate_newsletter.py` | Main CLI entry point |
| `pipeline/newsletter.py` | NewsletterDataQuery implementation |
| `templates/newsletter/` | Jinja2 templates for HTML/Markdown |
| `output/` | Generated newsletter output directory |
| `data.json` | Source movie database |

## Troubleshooting

### No Movies Found

If preview shows zero movies:
- Check that `data.json` has recent entries
- Verify the date range with `--days` flag
- Ensure movies have valid `discovered_date` values

### Template Errors

If rendering fails:
- Verify `templates/newsletter/` directory exists
- Check template syntax in `newsletter_base.html` and `newsletter_base.md`
- Enable `--debug` for detailed error messages

### Missing RT Scores

If many movies lack RT scores:
- Run the enrichment pipeline before newsletter generation
- Check RT scraper connectivity
- Verify title matching in enrichment logs

## Integration

Newsletter generation typically follows the daily discovery pipeline:
1. Discovery scripts fetch new releases
2. Enrichment adds RT scores and metadata
3. Admin curation reviews/approves content (`./launch_all.sh`)
4. Newsletter generator produces output
