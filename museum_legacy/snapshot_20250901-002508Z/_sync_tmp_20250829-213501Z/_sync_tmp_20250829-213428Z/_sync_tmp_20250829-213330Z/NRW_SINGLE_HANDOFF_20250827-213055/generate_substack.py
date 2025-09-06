import json
import yaml
from datetime import datetime, timedelta

def load_config():
    with open("config.yaml", "r") as f:
        return yaml.safe_load(f)

def generate_substack_newsletter():
    """Generate a Substack-ready newsletter from the latest data"""
    
    # Load the latest movie data (we'll use the HTML as source of truth)
    try:
        with open('output/site/index.html', 'r') as f:
            html_content = f.read()
            # Extract movie count from HTML
            import re
            movie_count = len(re.findall(r'class="card"', html_content))
    except:
        movie_count = 0
    
    # Create the newsletter
    today = datetime.now()
    week_start = (today - timedelta(days=7)).strftime("%B %d")
    week_end = today.strftime("%B %d, %Y")
    
    newsletter = f"""# 🎬 New Release Wall: {week_start} - {week_end}

*Your weekly guide to what's actually new on streaming*

---

## 📊 This Week at a Glance

**{movie_count} new digital releases** hit streaming platforms this week. Here's what's worth your time:

### 🏆 Critics' Picks
Films with 70%+ on Rotten Tomatoes or Metacritic

[PLACEHOLDER - Add 3-5 top reviewed films here]

### 🔥 Trending Now  
What everyone's watching

[PLACEHOLDER - Add 3-5 most popular films here]

### 💎 Hidden Gems
Under-the-radar releases worth discovering

[PLACEHOLDER - Add 2-3 interesting lesser-known films here]

---

## 🎯 Quick Picks by Mood

**Date Night:** [Film Title] - [One line description]
**Family Fun:** [Film Title] - [One line description]  
**Thrill Seeker:** [Film Title] - [One line description]
**Arthouse:** [Film Title] - [One line description]

---

## 📺 By Platform

### Netflix
- Film 1
- Film 2
- Film 3

### Amazon Prime Video
- Film 1
- Film 2

### Apple TV+
- Film 1
- Film 2

### Disney+/Hulu
- Film 1
- Film 2

---

## 🌍 International Corner

This week's best non-English releases:

1. **[Film Title]** (Country) - [Platform]
   *[One sentence description]*

2. **[Film Title]** (Country) - [Platform]
   *[One sentence description]*

---

## 📈 The Numbers

- **Total New Releases:** {movie_count}
- **With Critical Reviews:** [X]
- **Netflix Exclusives:** [X]
- **Foreign Language:** [X]
- **Documentary:** [X]

---

## 🔮 Coming Next Week

Get ready for:
- [Major upcoming release 1]
- [Major upcoming release 2]

---

*How was this week's selection? Reply and let me know what you watched!*

**[View the full New Release Wall →](https://hadrianbelove-stack.github.io/new-release-wall/)**

---

*You're receiving this because you subscribed to New Release Wall. [Unsubscribe]()*
"""
    
    # Save the newsletter
    with open('output/newsletter.md', 'w') as f:
        f.write(newsletter)
    
    # Also create a simplified list version
    simple_list = f"""# New Releases: {week_start} - {week_end}

## All {movie_count} Releases This Week

### With Reviews
- Film Title (RT: X%) - Netflix, Prime
- Film Title (RT: X%) - Apple TV+

### New to Streaming  
- Film Title - Netflix
- Film Title - Prime Video
- Film Title - Hulu

### International
- Film Title (Country) - Platform
- Film Title (Country) - Platform

---
[View Visual Wall](https://hadrianbelove-stack.github.io/new-release-wall/)
"""
    
    with open('output/simple_list.md', 'w') as f:
        f.write(simple_list)
    
    print(f"✓ Generated Substack newsletter: output/newsletter.md")
    print(f"✓ Generated simple list: output/simple_list.md")
    print(f"\nNewsletter includes {movie_count} movies from the past week")
    print("\nNext steps:")
    print("1. Open output/newsletter.md")
    print("2. Fill in the [PLACEHOLDER] sections with actual movies")
    print("3. Copy & paste into Substack")

if __name__ == "__main__":
    generate_substack_newsletter()
