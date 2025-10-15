#!/usr/bin/env python3
"""
Test Selenium setup - opens Google and searches for something
"""

from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from webdriver_manager.chrome import ChromeDriverManager
import time

def test_selenium():
    print("Setting up Chrome driver...")
    
    # Setup Chrome options
    chrome_options = Options()
    chrome_options.add_argument('--no-sandbox')
    chrome_options.add_argument('--disable-dev-shm-usage')
    # chrome_options.add_argument('--headless')  # Uncomment to run without browser window
    
    # Auto-download ChromeDriver
    service = Service(ChromeDriverManager().install())
    
    try:
        # Create browser instance
        print("Starting Chrome browser...")
        driver = webdriver.Chrome(service=service, options=chrome_options)
        
        # Test 1: Go to Google
        print("Testing: Opening Google...")
        driver.get("https://google.com")
        print(f"Page title: {driver.title}")
        
        # Test 2: Search for something
        print("Testing: Searching...")
        search_box = driver.find_element(By.NAME, "q")
        search_box.send_keys("selenium python")
        search_box.send_keys(Keys.RETURN)
        
        # Wait for results
        time.sleep(2)
        print(f"Results page title: {driver.title}")
        
        # Test 3: Count results
        results = driver.find_elements(By.CSS_SELECTOR, "h3")
        print(f"Found {len(results)} search results")
        
        print("✅ Selenium setup working perfectly!")
        return True
        
    except Exception as e:
        print(f"❌ Selenium setup failed: {e}")
        return False
        
    finally:
        if 'driver' in locals():
            print("Closing browser...")
            driver.quit()

if __name__ == "__main__":
    test_selenium()
