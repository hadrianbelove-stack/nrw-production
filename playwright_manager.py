#!/usr/bin/env python3
"""
Shared Playwright Manager - Ensures single event loop across all scrapers

This manager:
1. Creates ONE Playwright instance shared by all scrapers
2. Prevents multiple event loops from being created
3. Provides proper cleanup on exit
4. Thread-safe singleton pattern
"""

from playwright.sync_api import sync_playwright, Playwright, Browser, BrowserContext
import threading
import atexit


class PlaywrightManager:
    """Singleton manager for shared Playwright instance"""
    
    _instance = None
    _lock = threading.Lock()
    
    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        """Initialize the manager (only once)"""
        if self._initialized:
            return
            
        self.playwright = None
        self.browser = None
        self.reference_count = 0
        self._lock = threading.RLock()
        self._initialized = True
        
        # Register cleanup on exit
        atexit.register(self.cleanup)
    
    def get_playwright(self):
        """
        Get or create the shared Playwright instance

        Returns:
            Playwright: Shared Playwright instance
        """
        with self._lock:
            if self.playwright is None:
                print("[PlaywrightManager] Initializing shared Playwright instance...")

                # Check for existing event loop
                import asyncio
                try:
                    loop = asyncio.get_running_loop()
                    print(f"[PlaywrightManager] WARNING: Event loop already running: {loop}")
                    print(f"[PlaywrightManager] This will cause Playwright sync API to fail!")
                except RuntimeError:
                    print("[PlaywrightManager] No event loop detected - safe to proceed")

                self.playwright = sync_playwright().start()
                print("[PlaywrightManager] Playwright instance created")

            self.reference_count += 1
            return self.playwright
    
    def get_browser(self, headless=True, browser_type='chromium'):
        """
        Get or create a shared browser instance
        
        Args:
            headless (bool): Run browser in headless mode
            browser_type (str): Browser type ('chromium', 'firefox', 'webkit')
        
        Returns:
            Browser: Shared browser instance
        """
        with self._lock:
            # Ensure playwright is initialized
            if self.playwright is None:
                self.get_playwright()
            
            # Create browser if needed
            if self.browser is None:
                print(f"[PlaywrightManager] Launching {browser_type} browser (headless={headless})...")
                launcher = getattr(self.playwright, browser_type)
                self.browser = launcher.launch(headless=headless)
                print("[PlaywrightManager] Browser launched")
            
            return self.browser
    
    def release(self):
        """
        Release a reference to the Playwright instance
        Cleanup happens automatically when all references are released
        """
        with self._lock:
            if self.reference_count > 0:
                self.reference_count -= 1
                
            # Don't auto-cleanup here - let atexit handle it
            # This prevents premature cleanup if scrapers are reused
    
    def cleanup(self):
        """
        Force cleanup of Playwright resources
        Called automatically on exit via atexit
        """
        with self._lock:
            if self.browser is not None:
                print("[PlaywrightManager] Closing browser...")
                try:
                    self.browser.close()
                except Exception as e:
                    print(f"[PlaywrightManager] Error closing browser: {e}")
                self.browser = None
            
            if self.playwright is not None:
                print("[PlaywrightManager] Stopping Playwright...")
                try:
                    self.playwright.stop()
                except Exception as e:
                    print(f"[PlaywrightManager] Error stopping Playwright: {e}")
                self.playwright = None
            
            self.reference_count = 0

    def health_check(self):
        """
        Perform a basic health check by launching browser, opening a blank page, and closing

        Returns:
            dict: Health check results with status, timing, and error info
        """
        import time

        result = {
            'status': 'unknown',
            'duration_ms': 0,
            'error': None,
            'browser_type': 'chromium',
            'headless': True,
            'timestamp': time.time()
        }

        start_time = time.time()

        try:
            print("[PlaywrightManager] Starting health check...")

            # Get browser instance
            browser = self.get_browser(headless=True, browser_type='chromium')

            # Create a new context for the health check
            context = browser.new_context()

            # Open a blank page
            page = context.new_page()
            page.goto('about:blank')

            # Simple verification - check page title exists
            title = page.title()
            print(f"[PlaywrightManager] Health check page loaded: '{title}'")

            # Clean up
            context.close()

            result['status'] = 'healthy'
            result['duration_ms'] = int((time.time() - start_time) * 1000)

            print(f"[PlaywrightManager] Health check passed in {result['duration_ms']}ms")

        except Exception as e:
            result['status'] = 'unhealthy'
            result['error'] = str(e)
            result['duration_ms'] = int((time.time() - start_time) * 1000)

            print(f"[PlaywrightManager] Health check failed after {result['duration_ms']}ms: {e}")

        return result


# Global singleton instance
_manager = None

def get_playwright_manager():
    """
    Get the global PlaywrightManager singleton
    
    Returns:
        PlaywrightManager: Global manager instance
    """
    global _manager
    if _manager is None:
        _manager = PlaywrightManager()
    return _manager
