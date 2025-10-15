#!/usr/bin/env python3
"""
Selenium-based Wikidata scraper for getting precise RT and Wikipedia links
"""

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException
from webdriver_manager.chrome import ChromeDriverManager
import time
import re

class WikidataScraper:
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
    
    def get_wikidata_links(self, imdb_id):
        """Get Wikipedia and RT links from Wikidata using IMDb ID"""
        if not imdb_id:
            return None, None
        
        try:
            # Search for the IMDb ID in Wikidata
            search_url = f"https://www.wikidata.org/w/index.php?search={imdb_id}"
            self.driver.get(search_url)
            
            # Wait for search results
            time.sleep(2)
            
            # Look for search results with IMDb ID
            results = self.driver.find_elements(By.CSS_SELECTOR, ".mw-search-result")
            
            wikidata_url = None
            for result in results:
                try:
                    link_element = result.find_element(By.CSS_SELECTOR, ".mw-search-result-heading a")
                    if link_element:
                        wikidata_url = link_element.get_attribute('href')
                        break
                except NoSuchElementException:
                    continue
            
            if not wikidata_url:
                print(f"No Wikidata entity found for {imdb_id}")
                return None, None
            
            # Go to the Wikidata entity page
            self.driver.get(wikidata_url)
            time.sleep(2)
            
            # Extract Wikipedia link from sitelinks
            wikipedia_title = None
            try:
                # Look for English Wikipedia sitelink
                enwiki_section = self.driver.find_element(By.ID, "sitelinks-wikipedia")
                enwiki_links = enwiki_section.find_elements(By.CSS_SELECTOR, "a[hreflang='en']")
                
                for link in enwiki_links:
                    href = link.get_attribute('href')
                    if 'en.wikipedia.org/wiki/' in href:
                        # Extract title from URL
                        wikipedia_title = href.split('/wiki/')[-1]
                        break
            except NoSuchElementException:
                print(f"No English Wikipedia link found for {imdb_id}")
            
            # Extract Rotten Tomatoes ID from properties
            rt_id = None
            try:
                # Look for property P1258 (Rotten Tomatoes identifier)
                properties = self.driver.find_elements(By.CSS_SELECTOR, ".wikibase-statementgroupview")
                
                for prop_group in properties:
                    try:
                        prop_label = prop_group.find_element(By.CSS_SELECTOR, ".wikibase-statementgroupview-property-label")
                        if "Rotten Tomatoes" in prop_label.text:
                            rt_value = prop_group.find_element(By.CSS_SELECTOR, ".wikibase-snakview-value")
                            rt_id = rt_value.text.strip()
                            break
                    except NoSuchElementException:
                        continue
            except NoSuchElementException:
                print(f"No Rotten Tomatoes ID found for {imdb_id}")
            
            return wikipedia_title, rt_id
            
        except Exception as e:
            print(f"Wikidata scraping failed for {imdb_id}: {e}")
            return None, None
    
    def close(self):
        self.driver.quit()

def test_scraper():
    """Test the scraper with a known movie"""
    scraper = WikidataScraper(headless=False)  # Show browser for testing
    
    # Test with Landmarks IMDb ID
    wikipedia_title, rt_id = scraper.get_wikidata_links("tt9859510")
    print(f"Landmarks: Wikipedia='{wikipedia_title}', RT='{rt_id}'")
    
    scraper.close()

if __name__ == "__main__":
    test_scraper()