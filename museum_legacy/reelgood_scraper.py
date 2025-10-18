#!/usr/bin/env python3
"""
Reelgood scraper for movie digital release dates
"""

from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager
import time
import re

class ReelgoodScraper:
    def __init__(self, headless=True):
        self.setup_driver(headless)
    
    def setup_driver(self, headless):
        """Setup Chrome driver with options"""
        chrome_options = Options()
        if headless:
            chrome_options.add_argument('--headless')
        chrome_options.add_argument('--no-sandbox')
        chrome_options.add_argument('--disable-dev-shm-usage')
        chrome_options.add_argument('--disable-gpu')
        chrome_options.add_argument('--window-size=1920,1080')
        
        service = Service(ChromeDriverManager().install())
        self.driver = webdriver.Chrome(service=service, options=chrome_options)
        self.wait = WebDriverWait(self.driver, 10)
    
    def search_movie(self, movie_title):
        """Search for a movie on Reelgood"""
        try:
            print(f"Searching Reelgood for: {movie_title}")
            
            # Go to Reelgood
            self.driver.get("https://reelgood.com")
            time.sleep(2)
            
            # Find and use search
            search_input = self.wait.until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "[data-testid='search-input']"))
            )
            search_input.clear()
            search_input.send_keys(movie_title)
            search_input.send_keys(Keys.RETURN)
            
            # Wait for search results
            time.sleep(3)
            
            # Look for the first movie result
            try:
                # Try different selectors for movie cards
                movie_link = self.wait.until(
                    EC.element_to_be_clickable((By.CSS_SELECTOR, "[data-testid='title-card'], .title-card, .search-result"))
                )
                movie_link.click()
                time.sleep(2)
                
                # Look for availability information
                availability_info = self.extract_availability()
                return availability_info
                
            except Exception as e:
                print(f"No results found for {movie_title}: {e}")
                return None
                
        except Exception as e:
            print(f"Search failed for {movie_title}: {e}")
            return None
    
    def extract_availability(self):
        """Extract availability date from movie page"""
        try:
            # Look for various date patterns
            date_selectors = [
                "[data-testid='availability-date']",
                ".availability-date", 
                ".release-date",
                "*[contains(text(), 'Available')]",
                "*[contains(text(), 'Added')]"
            ]
            
            for selector in date_selectors:
                try:
                    elements = self.driver.find_elements(By.CSS_SELECTOR, selector)
                    for element in elements:
                        text = element.text
                        if text and ('available' in text.lower() or 'added' in text.lower()):
                            # Extract date from text like "Available since July 15, 2025"
                            date = self.parse_date_from_text(text)
                            if date:
                                return date
                except:
                    continue
            
            # Fallback: look in page source for date patterns
            page_source = self.driver.page_source
            date_patterns = [
                r'available since (\w+ \d{1,2}, \d{4})',
                r'added (\w+ \d{1,2}, \d{4})',
                r'(\d{4}-\d{2}-\d{2})'
            ]
            
            for pattern in date_patterns:
                match = re.search(pattern, page_source, re.IGNORECASE)
                if match:
                    return match.group(1)
            
            return None
            
        except Exception as e:
            print(f"Failed to extract availability: {e}")
            return None
    
    def parse_date_from_text(self, text):
        """Parse date from text like 'Available since July 15, 2025'"""
        date_pattern = r'(\w+ \d{1,2}, \d{4})'
        match = re.search(date_pattern, text)
        if match:
            return match.group(1)
        return None
    
    def close(self):
        """Close the browser"""
        if hasattr(self, 'driver'):
            self.driver.quit()

def test_scraper():
    """Test the scraper with a known movie"""
    scraper = ReelgoodScraper(headless=False)  # Show browser for testing
    
    try:
        # Test with a popular movie
        result = scraper.search_movie("Deadpool")
        print(f"Result: {result}")
        
    finally:
        scraper.close()

if __name__ == "__main__":
    test_scraper()
