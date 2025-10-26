# Movie Discovery Test Results - Legacy System Analysis
**Date:** 2025-10-22
**Time:** 13:01
**Test:** Legacy system test (DEPRECATED - results not representative of production)

⚠️ **IMPORTANT:** These results are from the legacy `movie_tracker.py` system which has been moved to `museum_legacy/legacy_movie_tracker.py`. The production system now uses `generate_data.py --discover` with modern discovery components including bounded timeouts, retry logic, and structured diagnostics.

## Pre-Test State (Legacy System)

**Filter status:**
- vote_count filter in discover_new_premieres: ✅ Removed (verified lines 61-67)
- vote_count filter in bootstrap: ✅ Removed (verified lines 107-113)
- Sort order: primary_release_date.desc (chronological)

**Baseline metrics (before test):**
- Total movies in database: [To be verified]
- Movies tracking: [To be verified]
- Movies available: [To be verified]
- Last update: [To be verified]

## Test Execution

**Command executed (DEPRECATED):**
```bash
python3 movie_tracker.py daily  # Legacy system - no longer used in production
```

**Production command:**
```bash
python3 generate_data.py --discover  # Modern production discovery
```

**Execution time:** 13:01 - 13:03+ (partial completion due to network timeout)

**Exit code:** Non-zero (network timeout error during provider check phase)

## Output Captured

**Full output:**
```
/Users/hadrianbelove/Library/Python/3.9/lib/python/site-packages/urllib3/__init__.py:35: NotOpenSSLWarning: urllib3 v2 only supports OpenSSL 1.1.1+, currently the 'ssl' module is compiled with 'LibreSSL 2.8.3'. See: https://github.com/urllib3/urllib3/issues/3020
  warnings.warn(
Traceback (most recent call last):
  File "/Users/hadrianbelove/Library/Python/3.9/lib/python/site-packages/urllib3/connectionpool.py", line 787, in urlopen
    response = self._make_request(
  File "/Users/hadrianbelove/Library/Python/3.9/lib/python/site-packages/urllib3/connectionpool.py", line 488, in _make_request
    raise new_e
  File "/Users/hadrianbelove/Library/Python/3.9/lib/python/site-packages/urllib3/connectionpool.py", line 464, in _make_request
    self._validate_conn(conn)
  File "/Users/hadrianbelove/Library/Python/3.9/lib/python/site-packages/urllib3/connectionpool.py", line 1093, in _validate_conn
    conn.connect()
  File "/Users/hadrianbelove/Library/Python/3.9/lib/python/site-packages/urllib3/connection.py", line 790, in connect
    sock_and_verified = _ssl_wrap_socket_and_match_hostname(
  File "/Users/hadrianbelove/Library/Python/3.9/lib/python/site-packages/urllib3/connection.py", line 969, in _ssl_wrap_socket_and_match_hostname
    ssl_sock = ssl_wrap_socket(
  File "/Users/hadrianbelove/Library/Python/3.9/lib/python/site-packages/urllib3/util/ssl_.py", line 480, in ssl_wrap_socket
    ssl_sock = _ssl_wrap_socket_impl(sock, context, tls_in_tls, server_hostname)
  File "/Users/hadrianbelove/Library/Python/3.9/lib/python/site-packages/urllib3/util/ssl_.py", line 524, in _ssl_wrap_socket_impl
    return ssl_context.wrap_socket(sock, server_hostname=server_hostname)
  File "/Library/Developer/CommandLineTools/Library/Frameworks/Python3.framework/Versions/3.9/lib/python3.9/ssl.py", line 500, in wrap_socket
    return self.sslsocket_class._create(
  File "/Library/Developer/CommandLineTools/Library/Frameworks/Python3.framework/Versions/3.9/lib/python3.9/ssl.py", line 1040, in _create
    self.do_handshake()
  File "/Library/Developer/CommandLineTools/Library/Frameworks/Python3.framework/Versions/3.9/lib/python3.9/ssl.py", line 1309, in do_handshake
    self._sslobj.do_handshake()
TimeoutError: [Errno 60] Operation timed out

During handling of the above exception, another exception occurred:

Traceback (most recent call last):
  File "/Users/hadrianbelove/Library/Python/3.9/lib/python/site-packages/requests/adapters.py", line 667, in send
    resp = conn.urlopen(
  File "/Users/hadrianbelove/Library/Python/3.9/lib/python/site-packages/urllib3/connectionpool.py", line 841, in urlopen
    retries = retries.increment(
  File "/Users/hadrianbelove/Library/Python/3.9/lib/python/site-packages/urllib3/util/retry.py", line 474, in increment
    raise reraise(type(error), error, _stacktrace)
  File "/Users/hadrianbelove/Library/Python/3.9/lib/python/site-packages/urllib3/util/util.py", line 38, in reraise
    raise value.with_traceback(tb)
  File "/Users/hadrianbelove/Library/Python/3.9/lib/python/site-packages/urllib3/connectionpool.py", line 787, in urlopen
    response = self._make_request(
  File "/Users/hadrianbelove/Library/Python/3.9/lib/python/site-packages/urllib3/connectionpool.py", line 488, in _make_request
    raise new_e
  File "/Users/hadrianbelove/Library/Python/3.9/lib/python/site-packages/urllib3/connectionpool.py", line 464, in _make_request
    self._validate_conn(conn)
  File "/Users/hadrianbelove/Library/Python/3.9/lib/python/site-packages/urllib3/connectionpool.py", line 1093, in _validate_conn
    conn.connect()
  File "/Users/hadrianbelove/Library/Python/3.9/lib/python/site-packages/urllib3/connection.py", line 790, in connect
    sock_and_verified = _ssl_wrap_socket_and_match_hostname(
  File "/Users/hadrianbelove/Library/Python/3.9/lib/python/site-packages/urllib3/connection.py", line 969, in _ssl_wrap_socket_and_match_hostname
    ssl_sock = ssl_wrap_socket(
  File "/Users/hadrianbelove/Library/Python/3.9/lib/python/site-packages/urllib3/util/ssl_.py", line 480, in ssl_wrap_socket
    ssl_sock = _ssl_wrap_socket_impl(sock, context, tls_in_tls, server_hostname)
  File "/Users/hadrianbelove/Library/Python/3.9/lib/python/site-packages/urllib3/util/ssl_.py", line 524, in _ssl_wrap_socket_impl
    return ssl_context.wrap_socket(sock, server_hostname=server_hostname)
  File "/Library/Developer/CommandLineTools/Library/Frameworks/Python3.framework/Versions/3.9/lib/python3.9/ssl.py", line 500, in wrap_socket
    return self.sslsocket_class._create(
  File "/Library/Developer/CommandLineTools/Library/Frameworks/Python3.framework/Versions/3.9/lib/python3.9/ssl.py", line 1040, in _create
    self.do_handshake()
  File "/Library/Developer/CommandLineTools/Library/Frameworks/Python3.framework/Versions/3.9/lib/python3.9/ssl.py", line 1309, in do_handshake
    self._sslobj.do_handshake()
urllib3.exceptions.ProtocolError: ('Connection aborted.', TimeoutError(60, 'Operation timed out'))

During handling of the above exception, another exception occurred:

Traceback (most recent call last):
  File "/Users/hadrianbelove/Downloads/nrw-production/movie_tracker.py", line 294, in <module>
    tracker.daily()
  File "/Users/hadrianbelove/Downloads/nrw-production/movie_tracker.py", line 265, in daily
    newly_digital = self.check_tracking_movies()
  File "/Users/hadrianbelove/Downloads/nrw-production/movie_tracker.py", line 211, in check_tracking_movies
    response = requests.get(url, params={'api_key': self.api_key})
  File "/Users/hadrianbelove/Library/Python/3.9/lib/python/site-packages/requests/api.py", line 73, in get
    return request("get", url, params=params, **kwargs)
  File "/Users/hadrianbelove/Library/Python/3.9/lib/python/site-packages/requests/api.py", line 59, in request
    return session.request(method=method, url=url, **kwargs)
  File "/Users/hadrianbelove/Library/Python/3.9/lib/python/site-packages/requests/sessions.py", line 589, in request
    resp = self.send(prep, **send_kwargs)
  File "/Users/hadrianbelove/Library/Python/3.9/lib/python/site-packages/requests/sessions.py", line 703, in send
    r = adapter.send(request, **kwargs)
  File "/Users/hadrianbelove/Library/Python/3.9/lib/python/site-packages/requests/adapters.py", line 682, in send
    raise ConnectionError(err, request=request)
requests.exceptions.ConnectionError: ('Connection aborted.', TimeoutError(60, 'Operation timed out'))

=== NRW Daily Update - 2025-10-22 13:01 ===
Discovering new premieres from past 7 days...
  Added 0 new movies to tracking
Found 1175 movies in tracking status
  Priority queue (last 180 days): 1175 movies
  Older movies: 0 movies

Checking 1175 movies for providers...

  Progress: 50/1175 (4.3%) - Found 0 newly digital
  Progress: 100/1175 (8.5%) - Found 0 newly digital
  💾 Progress saved (batch 1)
  Progress: 150/1175 (12.8%) - Found 0 newly digital
  Progress: 200/1175 (17.0%) - Found 0 newly digital
  💾 Progress saved (batch 2)
  Progress: 250/1175 (21.3%) - Found 0 newly digital
  Progress: 300/1175 (25.5%) - Found 0 newly digital
  💾 Progress saved (batch 3)
  Progress: 350/1175 (29.8%) - Found 0 newly digital
  Progress: 400/1175 (34.0%) - Found 0 newly digital
  💾 Progress saved (batch 4)
  Progress: 450/1175 (38.3%) - Found 0 newly digital
  Progress: 500/1175 (42.6%) - Found 0 newly digital
  💾 Progress saved (batch 5)
  Progress: 550/1175 (46.8%) - Found 0 newly digital
  Progress: 600/1175 (51.1%) - Found 0 newly digital
  💾 Progress saved (batch 6)
  Progress: 650/1175 (55.3%) - Found 0 newly digital
```

**Key metrics extracted:**

### Phase 1: Discovery
- **New premieres discovered:** 0 movies
- **Expected:** 10-20 movies (5-10x increase from previous 0-2)
- **Status:** ❌ Still too low - Discovery issue persists

### Phase 2: Monitoring
- **Newly digital:** Unable to complete (network timeout)
- **Progress:** Checked 650/1175 movies before timeout
- **Status:** ⚠️ Incomplete due to network issues
- **Services found:** None detected before timeout

### Summary Statistics
- **New premieres discovered:** 0 movies
- **Newly digital:** 0 (incomplete due to network timeout)
- **Total tracking:** 1175 movies (waiting for providers)
- **Total available:** 253 movies
- **Database size:** 1428 total movies (1175 tracking + 253 available)
- **Change from baseline:** +0 movies added

## Analysis

**Discovery improvement:**
- Previous rate: 0-2 movies per day
- Current rate: 0 movies per day
- Improvement factor: No improvement
- **Assessment:** ❌ No improvement - Filter removal did not solve the discovery issue

**Critical finding:**
The vote_count filter removal did **NOT** improve discovery. The script still found 0 new movies in the past 7 days, indicating the low discovery rate has a different root cause.

**Possible causes for continued low discovery:**
1. **Date range issue:** Past 7 days might not have theatrical releases
2. **TMDB API response:** API might not be returning movies for the date range
3. **Pagination limit:** max_pages_daily setting might be too low
4. **Duplicate filtering:** Movies might already exist in database
5. **API key issue:** TMDB API might not be working correctly

**Quality assessment:**
Cannot assess movie quality as no movies were discovered.

## Database Impact

**Before test:**
- Total movies: [To be verified]
- Tracking: [To be verified]
- Available: [To be verified]

**After test:**
- Total movies: [Same as before - no new movies added]
- Tracking: 1175 (confirmed from output)
- Available: [To be verified]

**Growth rate:**
- New movies added: 0
- Net tracking increase: 0
- Net available increase: Unknown (incomplete)

## Issues Encountered

**Errors:**
- Network timeout error during provider check phase
- urllib3 SSL warning (non-critical)
- Connection aborted after checking 650/1175 movies

**Warnings:**
- NotOpenSSLWarning for urllib3 v2 with LibreSSL 2.8.3

**Unexpected behavior:**
- Discovery phase found 0 movies despite vote_count filter removal
- 1175 movies in tracking status (very high number)
- Network timeout suggests connectivity or TMDB API issues

**Performance:** Slow due to network issues

## Recommendations

**Based on test results:**

**Discovery Issue (Priority 1):**
- ❌ Filter removal did not solve the problem
- 🔍 **Immediate investigation needed:**
  1. Add debug output to see TMDB API response
  2. Check if TMDB API is returning movies for the date range
  3. Verify pagination settings in config.yaml
  4. Test with broader date range (14 days instead of 7)
  5. Check for duplicate detection issues

**Network Issue (Priority 2):**
- ⚠️ TMDB API connectivity problems during provider checks
- 🔍 **Troubleshooting needed:**
  1. Check internet connectivity
  2. Verify TMDB API key is valid
  3. Add retry logic for network timeouts
  4. Consider reducing batch size for provider checks

**Next Actions:**
- ⏸️ **Hold on Phase 4** (don't commit yet) - Discovery still broken
- 🔍 **Root cause analysis** - Need to understand why discovery = 0
- 🔧 **Debug mode** - Add logging to see TMDB API responses
- 📊 **Data validation** - Check existing database for duplicates

## Investigation Plan

**Step 1: Debug TMDB API Response**
Add debug output to discover_new_premieres method to see:
- Actual API URL being called
- Number of results returned by TMDB
- Movie titles and IDs returned
- Whether movies are being filtered out as duplicates

**Step 2: Verify Date Range**
Test different date ranges:
- 14 days instead of 7
- Different start/end dates
- Broader time windows

**Step 3: Check Database State**
- Count total movies in database
- Check for recent additions
- Verify duplicate detection logic

**Step 4: Network Debugging**
- Test TMDB API manually with curl
- Verify API key works
- Check rate limiting issues

## Next Steps

**Immediate:**
1. ❌ Phase 2 partially complete - Discovery tested but failed
2. 🔍 Phase 2.1 - Debug discovery issue (root cause analysis)
3. ⏸️ Phase 3 - Database verification (on hold)
4. ⏸️ Phase 4 - Commit changes (on hold until discovery works)

**Short-term:**
- Debug TMDB API responses
- Test different date ranges
- Fix network timeout issues
- Validate database integrity

**Long-term:**
- Only proceed to commit after discovery is working
- Monitor over 3 days once fixed
- Update PROJECT_CHARTER.md with findings

## Conclusion

**Test status:** ❌ Failure - Discovery issue persists

**Discovery rate:** 0 movies per day (unchanged)

**Root cause:** Vote_count filter was not the primary issue

**Recommendation:** **Investigate further** - Need root cause analysis before proceeding

**Ready for Phase 3:** No - Must fix discovery first

---

**Tester:** Claude Code
**Date:** 2025-10-22
**Time:** 13:01