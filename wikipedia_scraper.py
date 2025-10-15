#!/usr/bin/env python3
"""Selenium-based Wikipedia scraper for finding movie pages"""

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException
from webdriver_manager.chrome import ChromeDriverManager
import time
import urllib.parse

class WikipediaScraper:
    def __init__(self, headless=True):
        self.options = Options()
        if headless:
            self.options.add_argument('--headless')
        self.options.add_argument('--no-sandbox')
        self.options.add_argument('--disable-dev-shm-usage')
        self.options.add_argument('--user-agent=Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)')
        
        self.driver = webdriver.Chrome(
            service=webdriver.chrome.service.Service(ChromeDriverManager().install()),
            options=self.options
        )
        self.wait = WebDriverWait(self.driver, 10)
    
    def find_wikipedia_url(self, title, year=None):
        """Search Wikipedia for movie page"""
        try:
            search_query = f"{title} {year} film" if year else f"{title} film"
            encoded_query = urllib.parse.quote(search_query)
            search_url = f"https://en.wikipedia.org/w/index.php?search={encoded_query}"
            
            print(f"Searching Wikipedia for: {search_query}")
            self.driver.get(search_url)
            time.sleep(2)
            
            # Check if we landed directly on an article
            if "/wiki/" in self.driver.current_url and "Special:Search" not in self.driver.current_url:
                print(f"Direct hit: {self.driver.current_url}")
                return self.driver.current_url
            
            # Look for search results
            try:
                results = self.driver.find_elements(By.CSS_SELECTOR, ".mw-search-result-heading a")
                
                for result in results[:3]:
                    href = result.get_attribute('href')
                    result_title = result.text.lower()
                    
                    if title.lower() in result_title:
                        if 'film' in result_title or str(year) in result_title:
                            print(f"Found match: {href}")
                            return href
                
                # If no film-specific match, take first result if title matches
                if results and title.lower() in results[0].text.lower():
                    return results[0].get_attribute('href')
                    
            except NoSuchElementException:
                pass
            
            return None
            
        except Exception as e:
            print(f"Wikipedia search failed for {title}: {e}")
            return None
    
    def close(self):
        self.driver.quit()