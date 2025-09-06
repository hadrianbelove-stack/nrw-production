"""DEPRECATED: Use canonical entry points (generate_site.py, build_from_approved.py). DO NOT RUN DIRECTLY."""
#!/usr/bin/env python3
from flask import Flask, render_template, request, jsonify
import json
from datetime import datetime, timedelta

app = Flask(__name__)

@app.route('/')
def index():
    """Admin grid view for curation"""
    # Load current releases
    with open('current_releases.json', 'r') as f:
        releases = json.load(f)
    
    # Load any existing curation decisions
    try:
        with open('curated_selections.json', 'r') as f:
            curated = json.load(f)
    except:
        curated = {}
    
    return render_template('admin.html', 
                         movies=releases, 
                         curated=curated)

@app.route('/curate', methods=['POST'])
def curate():
    """Save curation decision"""
    movie_id = request.json['movie_id']
    decision = request.json['decision']  # 'approve', 'reject', 'feature'
    
    # Load existing decisions
    try:
        with open('curated_selections.json', 'r') as f:
            curated = json.load(f)
    except:
        curated = {}
    
    curated[movie_id] = {
        'decision': decision,
        'timestamp': datetime.now().isoformat()
    }
    
    with open('curated_selections.json', 'w') as f:
        json.dump(curated, f, indent=2)
    
    return jsonify({'status': 'success'})

@app.route('/publish', methods=['POST'])
def publish():
    """Generate final curated list"""
    # This would filter releases based on curation decisions
    # and regenerate the website with only approved films
    pass

if __name__ == '__main__':
    app.run(debug=True, port=5000)
