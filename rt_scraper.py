#!/usr/bin/env python3
"""
Selenium-based Rotten Tomatoes scraper for finding exact movie URLs
"""

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException
from webdriver_manager.chrome import ChromeDriverManager
import time
import urllib.parse

class RTScraper:
    def __init__(self, headless=True):
        self.options = Options()
        if headless:
            self.options.add_argument('--headless')
        self.options.add_argument('--no-sandbox')
        self.options.add_argument('--disable-dev-shm-usage')
        self.options.add_argument('--user-agent=Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36')
        
        self.driver = webdriver.Chrome(
            service=webdriver.chrome.service.Service(ChromeDriverManager().install()),
            options=self.options
        )
        self.wait = WebDriverWait(self.driver, 10)
    
    def find_movie_url(self, title, year=None):
        """Search RT for exact movie URL"""
        try:
            # Include year in search for better accuracy
            search_query = f"{title} {year}" if year else title
            encoded_query = urllib.parse.quote_plus(search_query)
            search_url = f"https://www.rottentomatoes.com/search?search={encoded_query}"
            
            print(f"Searching RT for: {search_query}")
            self.driver.get(search_url)
            time.sleep(4)  # Give page time to load
            
            # Updated selectors for current RT structure
            try:
                # Wait for movie results section
                self.wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "[data-qa='search-result']")))
                
                # Find all movie results (not TV)
                movie_sections = self.driver.find_elements(By.XPATH, "//search-page-result[@type='movie']")
                
                for section in movie_sections:
                    try:
                        # Get the link element within this movie result
                        link = section.find_element(By.CSS_SELECTOR, "a[data-qa='info-name']")
                        result_title = link.text.strip().lower()
                        href = link.get_attribute('href')
                        
                        # Check if title matches (fuzzy match)
                        if title.lower() in result_title or result_title in title.lower():
                            if '/m/' in href:  # Ensure it's a movie URL
                                print(f"Found RT URL: {href}")
                                return href
                                
                    except NoSuchElementException:
                        continue
                        
            except TimeoutException:
                print("Search results didn't load properly")
                
            return None
            
        except Exception as e:
            print(f"RT search failed for {title}: {e}")
            return None
    
    def get_movie_data(self, title, year=None):
        """Get both URL and score from RT"""
        try:
            url = self.find_movie_url(title, year)
            if not url:
                return None, None
                
            # Navigate to the movie page
            self.driver.get(url)
            time.sleep(2)
            
            # Try to find the Tomatometer score
            score = None
            try:
                # Multiple possible selectors for RT score
                score_element = self.driver.find_element(By.CSS_SELECTOR, 
                    "[data-qa='tomatometer-value'], .tomatometer-score, [slot='criticsScore']")
                score_text = score_element.text.strip()
                if score_text and '%' in score_text:
                    score = score_text
                elif score_text.isdigit():
                    score = f"{score_text}%"
            except NoSuchElementException:
                print(f"No score found for {title}")
                
            return url, score
            
        except Exception as e:
            print(f"Failed to get RT data for {title}: {e}")
            return None, None

    def close(self):
        self.driver.quit()

def test_rt_scraper():
    """Test the RT scraper with known movies"""
    scraper = RTScraper(headless=False)  # Show browser for testing
    
    # Test with a few movies
    test_movies = [
        ("Landmarks", 2025),
        ("Inspector Zende", 2025),
        ("The Substance", 2024)  # Known movie for comparison
    ]
    
    for title, year in test_movies:
        url = scraper.find_movie_url(title, year)
        print(f"{title} ({year}): {url}")
        time.sleep(2)  # Be respectful to RT
    
    scraper.close()

if __name__ == "__main__":
    test_rt_scraper()