# Design Archive

This directory contains archived UI prototypes, design mockups, and experimental HTML files from the NRW project's evolution.

## Purpose

Design files are archived here when:
- They were used for design exploration but not adopted
- They represent historical UI approaches that have been superseded
- They have reference value for understanding design decisions
- They are no longer operational but worth preserving

## Archived Files

### mockup_2025-10-25.html
- **Created:** October 25, 2025
- **Purpose:** UI design mockup showing card back button layouts with real platform logos
- **Content:** Examples of streaming/purchase button variations (Netflix, Prime, Max, Amazon, Apple)
- **Status:** Design exploration - informed current button implementation in index.html
- **Reference value:** Shows button styling evolution, platform logo integration approach

### mockup_card_back_2025-10-25.html
- **Created:** October 25, 2025
- **Purpose:** Design comparison mockup (CURRENT vs PROPOSED button designs)
- **Content:** Side-by-side comparison of "Rent/Buy" vs "Platform Name" button approaches
- **Decision:** Platform name approach was NOT adopted - kept generic "STREAM/RENT/BUY" buttons
- **Reference value:** Documents UI decision-making process, shows rejected design alternatives
- **Design notes included:** Explains button logic, priority, colors, affiliate links, click behavior

### newsletter_sample_2025-10-19.html
- **Created:** October 19, 2025
- **Purpose:** Sample newsletter output for testing and reference
- **Content:** Complete newsletter with Top Picks, Hidden Gems, By Genre sections (61 movies)
- **Status:** Reference sample - newsletter format has evolved since this version
- **Reference value:** Shows newsletter structure, useful for understanding format evolution
- **Note:** For current newsletter format, generate fresh with `python3 substack_newsletter_generator.py weekly`

### site_base.html
- **Created:** Earlier (pre-October 2025)
- **Purpose:** Base HTML template for site generation
- **Status:** Legacy template from earlier site generation approach
- **Note:** Predates current index.html structure

### site_base.html.bak
- **Created:** Earlier (pre-October 2025)
- **Purpose:** Backup of site_base.html
- **Status:** Legacy backup

## Current Operational Files

For current UI implementation, see:
- `/index.html` - Production website
- `/assets/app.js` - Frontend JavaScript
- `/assets/styles.css` - Current styling
- `/newsletters/` - Generated newsletters (current format)

## Design Evolution Notes

**Button Design (Oct 25, 2025):**
- Explored platform-specific buttons (NETFLIX, AMAZON, APPLE TV)
- Decided to keep generic action buttons (STREAM, RENT, BUY)
- Rationale: Actions are clearer than platform names for users
- See mockup_card_back_2025-10-25.html for detailed comparison

**Newsletter Format (Oct 19, 2025):**
- Established structure: Top Picks → Hidden Gems → By Genre → Alphabetical
- Format has evolved since this sample (new sections, improved styling)
- See newsletter_sample_2025-10-19.html for original format

## Notes

- These files are preserved for historical reference and design archaeology
- They are NOT operational and should not be used for current development
- For current design guidelines, see the operational files listed above
- For design decisions and rationale, see PROJECT_CHARTER.md amendments

**Last Updated:** 2025-11-06