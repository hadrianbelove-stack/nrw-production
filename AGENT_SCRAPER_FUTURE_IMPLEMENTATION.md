# Agent Scraper Future Implementation Guide (Path B)

**Created**: October 19, 2025
**Purpose**: Reference document for implementing authentication-based agent scraping if needed in the future
**Status**: Documentation only - not currently implemented

## Overview

The agent scraper was disabled on October 19, 2025, due to authentication barriers on all major streaming platforms. This document preserves the research and planning for implementing authentication-based scraping (Path B) should it become necessary in the future.

### Why Agent Scraper Was Disabled

- **Authentication walls**: All platforms (Netflix, Disney+, HBO Max/Max, Hulu) require login to access search results
- **Anti-bot detection**: Netflix actively detects automated browsers with reCAPTCHA and verification codes
- **100% failure rate**: 71 scraping attempts resulted in 0 successful link retrievals
- **Watchmode API sufficient**: Already integrated and provides same data without authentication challenges

### When to Consider Re-enabling

- Watchmode API becomes unavailable or too expensive
- Need for real-time data beyond API capabilities
- Platform-specific features required that APIs don't provide
- Business requirements demand direct platform integration

## Technical Requirements

### Core Dependencies

```python
# Required packages (add to requirements.txt)
playwright-stealth>=1.0.0  # Stealth plugin for Playwright
python-dotenv>=1.0.0      # Environment variable management
cryptography>=41.0.0      # For secure credential storage
```

### Browser Stealth Configuration

```python
# Stealth plugins to avoid detection
from playwright_stealth import stealth_sync

# Apply stealth to browser context
async def create_stealth_browser():
    browser = await playwright.chromium.launch(
        headless=False,  # Headless mode often detected
        args=[
            '--disable-blink-features=AutomationControlled',
            '--disable-dev-shm-usage',
            '--disable-web-security',
            '--disable-features=IsolateOrigins,site-per-process',
            '--disable-site-isolation-trials'
        ]
    )
    context = await browser.new_context(
        viewport={'width': 1920, 'height': 1080},
        user_agent='Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
    )
    await stealth_sync(context)
    return browser, context
```

### Session Management

```python
# Cookie persistence for maintaining login sessions
import json
import os

class SessionManager:
    def __init__(self, platform: str):
        self.platform = platform
        self.cookie_file = f'cache/cookies/{platform}_cookies.json'

    async def save_cookies(self, context):
        cookies = await context.cookies()
        os.makedirs(os.path.dirname(self.cookie_file), exist_ok=True)
        with open(self.cookie_file, 'w') as f:
            json.dump(cookies, f)

    async def load_cookies(self, context):
        if os.path.exists(self.cookie_file):
            with open(self.cookie_file, 'r') as f:
                cookies = json.load(f)
                await context.add_cookies(cookies)
                return True
        return False

    async def validate_session(self, page):
        # Platform-specific session validation
        if self.platform == 'netflix':
            return await page.locator('[data-uia="header-profile-link"]').is_visible()
        elif self.platform == 'disney':
            return await page.locator('.account-avatar').is_visible()
        # Add other platforms...
```

## Implementation Steps

### 1. Install Stealth Plugins

```bash
# Install required packages
pip install playwright-stealth python-dotenv cryptography

# Verify installation
python -c "from playwright_stealth import stealth_sync; print('Stealth plugin ready')"
```

### 2. Create Authentication Module

Create `auth_manager.py`:

```python
import os
from dotenv import load_dotenv
from playwright.async_api import Page
import asyncio
from typing import Optional

load_dotenv()

class AuthManager:
    def __init__(self):
        self.credentials = {
            'netflix': {
                'email': os.getenv('NETFLIX_EMAIL'),
                'password': os.getenv('NETFLIX_PASSWORD')
            },
            'disney': {
                'email': os.getenv('DISNEY_EMAIL'),
                'password': os.getenv('DISNEY_PASSWORD')
            },
            'max': {
                'email': os.getenv('MAX_EMAIL'),
                'password': os.getenv('MAX_PASSWORD')
            },
            'hulu': {
                'email': os.getenv('HULU_EMAIL'),
                'password': os.getenv('HULU_PASSWORD')
            }
        }

    async def login_netflix(self, page: Page) -> bool:
        try:
            await page.goto('https://www.netflix.com/login')
            await page.fill('input[name="userLoginId"]', self.credentials['netflix']['email'])
            await page.fill('input[name="password"]', self.credentials['netflix']['password'])
            await page.click('button[type="submit"]')

            # Wait for login to complete
            await page.wait_for_url('https://www.netflix.com/browse', timeout=10000)
            return True
        except Exception as e:
            print(f"Netflix login failed: {e}")
            return False

    async def login_disney(self, page: Page) -> bool:
        try:
            await page.goto('https://www.disneyplus.com/login')
            await page.fill('input[type="email"]', self.credentials['disney']['email'])
            await page.click('button[type="submit"]')
            await asyncio.sleep(1)  # Wait for password field
            await page.fill('input[type="password"]', self.credentials['disney']['password'])
            await page.click('button[type="submit"]')

            # Wait for home page
            await page.wait_for_url('**/home', timeout=10000)
            return True
        except Exception as e:
            print(f"Disney+ login failed: {e}")
            return False

    # Add login methods for Max and Hulu...
```

### 3. Store Credentials Securely

Create `.env` file (never commit to git):

```env
# Streaming Platform Credentials
NETFLIX_EMAIL=your_email@example.com
NETFLIX_PASSWORD=your_password
DISNEY_EMAIL=your_email@example.com
DISNEY_PASSWORD=your_password
MAX_EMAIL=your_email@example.com
MAX_PASSWORD=your_password
HULU_EMAIL=your_email@example.com
HULU_PASSWORD=your_password
```

Add to `.gitignore`:

```gitignore
.env
cache/cookies/
```

### 4. Update agent_link_scraper.py

Modify the scraper to use authentication:

```python
class AgentLinkScraper:
    def __init__(self, config):
        self.config = config
        self.auth_manager = AuthManager()
        self.session_manager = {}

    async def _ensure_authenticated(self, platform: str, page: Page) -> bool:
        """Ensure we're logged into the platform"""

        # Try to load existing session
        if platform not in self.session_manager:
            self.session_manager[platform] = SessionManager(platform)

        session = self.session_manager[platform]

        # Load cookies if available
        if await session.load_cookies(page.context):
            if await session.validate_session(page):
                return True

        # Login required
        login_method = getattr(self.auth_manager, f'login_{platform}', None)
        if login_method:
            success = await login_method(page)
            if success:
                await session.save_cookies(page.context)
                return True

        return False

    async def find_watch_link(self, movie_title: str, service: str) -> Optional[str]:
        """Find watch link with authentication"""

        platform = self._normalize_platform(service)

        async with self._create_stealth_browser() as (browser, context):
            page = await context.new_page()

            # Ensure authenticated
            if not await self._ensure_authenticated(platform, page):
                print(f"Authentication failed for {platform}")
                return None

            # Now perform the search (existing logic)
            # ...
```

### 5. Add Login Retry Logic

```python
class RetryableAuth:
    def __init__(self, max_retries: int = 3):
        self.max_retries = max_retries

    async def login_with_retry(self, login_func, page, platform):
        for attempt in range(self.max_retries):
            try:
                if await login_func(page):
                    return True

                # Wait with exponential backoff
                wait_time = 2 ** attempt
                print(f"Login attempt {attempt + 1} failed for {platform}, waiting {wait_time}s")
                await asyncio.sleep(wait_time)

            except Exception as e:
                print(f"Login exception for {platform}: {e}")

        return False
```

### 6. Update Selectors for Authenticated Pages

Authenticated pages may have different HTML structure:

```python
AUTHENTICATED_SELECTORS = {
    'netflix': [
        '[data-uia="search-result-title-link"]',  # Authenticated search results
        '.title-card-container a',
        '[data-testid="title-card-link"]'
    ],
    'disney': [
        '[data-testid="search-result-link"]',
        '.search-result-item a',
        '[data-gv2-asset-id] a'
    ],
    'max': [
        '[data-testid="content-card"] a',
        '.content-card-link',
        '[data-content-id] a'
    ],
    'hulu': [
        '[data-automationid="search-result"] a',
        '.CollectionItem__link',
        '[data-testid="tile-link"]'
    ]
}
```

## Platform-Specific Considerations

### Netflix
- **Authentication**: Email/password login
- **2FA**: May require handling verification codes sent via email/SMS
- **Bot Detection**: Most aggressive - uses multiple detection methods
- **Session Duration**: Cookies valid for ~30 days
- **Rate Limiting**: Aggressive - max 1 search every 5-10 seconds

### Disney+
- **Authentication**: Email/password login
- **2FA**: Optional but may be enforced for suspicious logins
- **Bot Detection**: Moderate - mainly user-agent and behavior patterns
- **Session Duration**: Cookies valid for ~14 days
- **Rate Limiting**: Moderate - max 1 search every 2-3 seconds

### HBO Max / Max
- **Rebranding**: Service renamed from "HBO Max" to "Max" in 2023
- **Authentication**: Email/password or provider login
- **2FA**: Depends on account settings
- **Bot Detection**: Minimal compared to Netflix
- **Session Duration**: Cookies valid for ~7 days
- **URLs**: Update from `hbomax.com` to `max.com`

### Hulu
- **Authentication**: Email/password or bundle login (Disney+)
- **2FA**: Optional but may be required
- **Bot Detection**: Moderate - similar to Disney+
- **Session Duration**: Cookies valid for ~30 days
- **Geographic Restrictions**: US-only service

## Risks and Challenges

### Legal and Compliance
- **Terms of Service**: Most platforms explicitly prohibit automated access
- **Account Risk**: Accounts may be suspended or banned if detected
- **Legal Liability**: Potential violation of Computer Fraud and Abuse Act (CFAA)
- **DMCA Concerns**: Circumventing access controls may violate DMCA

### Technical Challenges
- **Maintenance Burden**: Platforms change frequently (every 1-3 months)
- **Detection Arms Race**: Anti-bot measures constantly evolving
- **2FA Complexity**: Requires email/SMS integration or manual intervention
- **IP Blocking**: May require residential proxies ($$$)
- **Browser Fingerprinting**: Increasingly sophisticated detection methods

### Operational Concerns
- **Credential Management**: Secure storage and rotation required
- **Session Management**: Handle expired sessions gracefully
- **Error Recovery**: Must handle login failures, captchas, verification
- **Monitoring**: Need alerts for authentication failures
- **Cost**: Premium accounts needed for each platform (~$50-100/month total)

## Testing Strategy

### 1. Manual Verification First

Before automating, manually verify:
- Login flow for each platform
- Search result structure when authenticated
- Selector accuracy on authenticated pages
- Session cookie persistence

### 2. Isolated Testing

Test each platform in isolation:

```python
# test_auth_netflix.py
async def test_netflix_auth():
    scraper = AgentLinkScraper(config)
    link = await scraper.find_watch_link("Stranger Things", "Netflix")
    assert link is not None
    assert "netflix.com/title/" in link
```

### 3. Session Persistence Testing

```python
# test_session_persistence.py
async def test_session_reuse():
    scraper = AgentLinkScraper(config)

    # First request - should login
    link1 = await scraper.find_watch_link("Movie 1", "Netflix")

    # Second request - should use saved session
    link2 = await scraper.find_watch_link("Movie 2", "Netflix")

    # Verify both succeeded without re-login
    assert link1 and link2
```

### 4. Failure Recovery Testing

```python
# test_failure_recovery.py
async def test_login_failure_fallback():
    scraper = AgentLinkScraper(config)

    # Simulate login failure
    scraper.auth_manager.credentials['netflix']['password'] = 'wrong'

    link = await scraper.find_watch_link("Test Movie", "Netflix")

    # Should fallback to Watchmode API
    assert link is None or "watchmode.com" in link
```

### 5. Anti-Detection Monitoring

Monitor for signs of detection:
- Increased captcha challenges
- Account warnings or emails
- Sudden authentication failures
- IP blocks or rate limiting

## Alternative Solutions

### 1. Continue Using Watchmode API (Current - Recommended)
- **Pros**: No authentication needed, stable, legal, maintained
- **Cons**: Costs money at scale, depends on third party
- **Status**: Currently implemented and working

### 2. Partner with Platforms
- **Pros**: Official support, legal, reliable
- **Cons**: Difficult to obtain, may require revenue sharing
- **Approach**: Contact developer relations teams

### 3. Browser Extension Approach
- **Pros**: Uses real user sessions, harder to detect
- **Cons**: Requires user installation, privacy concerns
- **Implementation**: Chrome/Firefox extension that shares watch links

### 4. Crowd-sourced Data
- **Pros**: No scraping needed, community-driven
- **Cons**: Data quality issues, requires user base
- **Implementation**: Allow users to submit/verify watch links

### 5. Manual Curation
- **Pros**: 100% accurate, no technical complexity
- **Cons**: Labor intensive, doesn't scale
- **Use Case**: High-priority movies only

## Code References

### Current Implementation Files
- `agent_link_scraper.py`: Main scraper implementation (lines 1-300)
- `test_agent_scraper.py`: Testing framework
- `config.yaml`: Configuration (agent_scraper section, lines 20-32)
- `generate_data.py`: Integration point (lines 87-123, 1075-1113)

### Cache and Data Files
- `cache/agent_links_cache.json`: Historical scraping attempts
- `cache/screenshots/`: Failure diagnostics
- `cache/cookies/`: Would store session cookies (create if implementing)

### Related Documentation
- `AGENT_SCRAPER_DIAGNOSTICS.md`: Analysis of why scraper was disabled
- `DAILY_CONTEXT.md`: Current system state and decisions
- `PROJECT_CHARTER.md`: Governance and architectural decisions

## Conclusion

Implementing authentication-based agent scraping is technically feasible but comes with significant challenges:

1. **High complexity**: Requires authentication, session management, and anti-detection measures
2. **Maintenance burden**: Platforms change frequently, requiring constant updates
3. **Legal risks**: May violate Terms of Service and various laws
4. **Operational costs**: Requires accounts, proxies, and monitoring

**Recommendation**: Continue using Watchmode API unless business requirements absolutely demand direct platform integration. If implementation becomes necessary, start with one platform (suggest HBO Max/Max as least restrictive) and validate the approach before expanding.

**Reference**: See `AGENT_SCRAPER_DIAGNOSTICS.md` for the diagnostic analysis that led to disabling the agent scraper.