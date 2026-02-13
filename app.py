from flask import Flask, render_template, jsonify
from flask_cors import CORS
import requests
from datetime import datetime
import threading
import time
from collections import deque
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)
CORS(app)

SITES = {
    'Self-Service': 'https://apps.uillinois.edu/selfservice',
    'Canvas': 'https://canvas.illinois.edu',
    'MyIllini': 'https://myillini.illinois.edu',
    'Course Explorer': 'https://courses.illinois.edu',
    'UIUC Status': 'https://status.illinois.edu',
    'Media Space': 'https://mediaspace.illinois.edu',
    'APPS Directory': 'https://apps.uillinois.edu',
    'Illinois.edu': 'https://illinois.edu',
    'Student Affairs': 'https://studentaffairs.illinois.edu',
    'Admissions': 'https://admissions.illinois.edu',
    'University Housing': 'https://housing.illinois.edu',
    'Library': 'https://library.illinois.edu',
    'Technology Services': 'https://techservices.illinois.edu',
    'Box': 'https://uofi.box.com',
    'Webstore': 'https://webstore.illinois.edu'
}

# HISTORY CONFIGURATION
# We want 10 minutes of data with 30-second intervals.
# 10 mins * 60 secs / 30 secs = 20 data points.
HISTORY_LEN = 20
status_history = {site: deque(maxlen=HISTORY_LEN) for site in SITES}
current_status = {}
last_check_time = None

def check_website(name, url):
    try:
        start_time = time.time()
        headers = {'User-Agent': 'UIUC-Status-Monitor/1.0'}
        response = requests.get(url, timeout=5, allow_redirects=True, headers=headers)
        # Calculate response time in ms
        response_time = round((time.time() - start_time) * 1000)
        
        is_up = response.status_code == 200
        return {
            'status': 'up' if is_up else 'down',
            'code': response.status_code,
            'time': response_time, # Sending 'time' specifically for the graph
            'timestamp': datetime.now().isoformat()
        }
    except Exception as e:
        logger.error(f"Error checking {name}: {e}")
        return {
            'status': 'down',
            'error': str(e),
            'time': 0, # 0 ms indicates failure/timeout for graph
            'timestamp': datetime.now().isoformat()
        }

def monitor_loop():
    global last_check_time
    logger.info("Monitor thread started")
    while True:
        try:
            for name, url in SITES.items():
                result = check_website(name, url)
                current_status[name] = result
                status_history[name].append(result)
            
            last_check_time = datetime.now()
            logger.info(f"Check complete at {last_check_time}")
            
        except Exception as e:
            logger.error(f"Error in monitor loop: {e}")
        
        # SLEEP 30 SECONDS (Required for the 30s bar interval)
        time.sleep(30)

monitor_thread = threading.Thread(target=monitor_loop, daemon=True)
monitor_thread.start()

def get_stats_payload():
    """Helper to structure data for both initial load and API"""
    payload_sites = {}
    
    for name in SITES:
        history = list(status_history[name])
        
        # 1. Uptime calc
        if history:
            up_count = sum(1 for h in history if h['status'] == 'up')
            uptime_pct = round((up_count / len(history)) * 100, 2)
        else:
            uptime_pct = 0.0

        # 2. Get most recent status
        latest = current_status.get(name, {})
        
        # 3. Simplify history for the frontend graph (just the times and status)
        # We assume the list is chronological.
        graph_data = [{'time': h.get('time', 0), 'status': h['status']} for h in history]

        payload_sites[name] = {
            'status': latest.get('status', 'unknown'),
            'response_time': latest.get('time', 0),
            'uptime': uptime_pct,
            'history': graph_data,
            'url': SITES[name]
        }

    return {
        'sites': payload_sites,
        'last_check': last_check_time.isoformat() if last_check_time else None
    }

@app.route('/')
def index():
    return render_template('index.html', initial_data=get_stats_payload())

@app.route('/api/status')
def get_status():
    return jsonify(get_stats_payload())

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)