import hashlib
from flask import Flask, render_template, Response, request
import json
import os
import sys
import threading
import time
import logging
import traceback
from datetime import datetime
from flask_cors import CORS

# Add parent directory to sys.path to import demo_yield
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(BASE_DIR)
from retriever import get_articles_from_query
from LLM_GLM import bouncer_preset_chat, glm_preset_chat
from prompt import generate_full_prompt

app = Flask(__name__)
# Configure CORS to allow the custom tunnel headers used by the frontend
CORS(app, resources={r"/api/*": {"origins": "*", "allow_headers": ["ngrok-skip-browser-warning", "Bypass-Tunnel-Reminder", "Accept", "Content-Type"]}})

# --- Setup Daily Action Logger ---
LOGS_DIR = os.path.join(BASE_DIR, 'logs_action')
FEEDBACK_DIR = os.path.join(BASE_DIR, 'feedback')
os.makedirs(LOGS_DIR, exist_ok=True)
os.makedirs(FEEDBACK_DIR, exist_ok=True)

class DailyLogHandler(logging.FileHandler):
    def __init__(self):
        super().__init__(self.get_filename(), encoding='utf-8')
    def get_filename(self):
        return os.path.join(LOGS_DIR, f"{datetime.now().strftime('%Y-%m-%d')}.log")
    def emit(self, record):
        self.baseFilename = self.get_filename()
        self.stream = self._open()
        super().emit(record)

action_logger = logging.getLogger('action_logger')
action_logger.setLevel(logging.INFO)
log_formatter = logging.Formatter('%(asctime)s | [%(levelname)s] | %(message)s')
daily_handler = DailyLogHandler()
daily_handler.setFormatter(log_formatter)
action_logger.addHandler(daily_handler)

def log_event(level, msg, context, ip="System", perf_ms=None, error=None):
    log_str = f"Source: {context} | IP: {ip} | Message: {msg}"
    if perf_ms is not None:
        log_str += f" | Perf_ms: {int(perf_ms)}"
    if error:
        log_str += f" | Error: \n{error}"
        
    if level == "INFO":
        action_logger.info(log_str)
    elif level == "WARNING":
        action_logger.warning(log_str)
    elif level == "ERROR":
        action_logger.error(log_str)
    elif level == "FATAL":
        action_logger.critical(log_str)


def save_feedback_entry(payload, client_ip, user_agent):
    feedback_text = str(payload.get("message", "")).strip()
    rating = payload.get("rating")
    page = str(payload.get("page", "")).strip()
    query = str(payload.get("query", "")).strip()

    if not feedback_text:
        raise ValueError("Feedback message cannot be empty.")

    record = {
        "timestamp": datetime.now().isoformat(timespec="seconds"),
        "ip": client_ip,
        "user_agent": user_agent,
        "message": feedback_text,
        "rating": rating,
        "page": page,
        "query": query,
    }

    feedback_file = os.path.join(FEEDBACK_DIR, f"{datetime.now().strftime('%Y-%m-%d')}.jsonl")
    with open(feedback_file, "a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=False) + "\n")

    return record

# --- Background Job Manager ---
# This decouples the LLM processing from the HTTP request, so if the browser reloads
# or disconnects, the AI keeps running. When reconnecting via the same query, it replays the history.
MAX_CONCURRENT_JOBS = 5  # Change this value to restrict the number of concurrently tracing users
job_store = {}
job_lock = threading.Lock()

def run_background_pipeline(query, job, client_ip):
    start_time = time.time()
    log_event("INFO", f"Started background pipeline for query '{query}'", "run_background_pipeline", ip=client_ip)
    try:
        job['events'].append({'type': 'progress', 'message': 'Validating your query...'})
        with job['condition']:
            job['condition'].notify_all()

        bouncer_start = time.time()
        bouncer_result = bouncer_preset_chat(query)
        log_event("INFO", "Bouncer validation completed", "run_background_pipeline:bouncer_preset_chat", ip=client_ip, perf_ms=(time.time() - bouncer_start) * 1000)

        if not bouncer_result.get("is_valid", False):
            job['events'].append({
                'type': 'bouncer_invalid',
                'message': bouncer_result.get('rejection_reason', 'Your query was rejected.')
            })
            job['status'] = 'completed'
            with job['condition']:
                job['condition'].notify_all()
            log_event("WARNING", f"Query '{query}' rejected: {bouncer_result.get('rejection_reason')}", "run_background_pipeline", ip=client_ip, perf_ms=(time.time() - start_time) * 1000)
            return

        job['events'].append({'type': 'progress', 'message': 'Searching dataset for relevant newspaper articles...'})
        with job['condition']:
            job['condition'].notify_all()
        
        search_start = time.time()
        articles = get_articles_from_query(query, 100)
        log_event("INFO", f"Fetched {len(articles)} articles", "run_background_pipeline:get_articles_from_query", ip=client_ip, perf_ms=(time.time() - search_start) * 1000)

        # Emit retrieval trace to clients (sorted by similarity score descending)
        try:
            articles_sorted = sorted(articles, key=lambda x: x.get('score', 0), reverse=True)
            job['events'].append({'type': 'retrieval', 'articles': articles_sorted})
            with job['condition']:
                job['condition'].notify_all()
        except Exception as e:
            log_event('ERROR', f'Failed to emit retrieval trace: {e}', 'run_background_pipeline', ip=client_ip, error=traceback.format_exc())

        if len(articles) == 0:
            job['events'].append({'type': 'progress', 'message': 'No relevant articles found in the dataset. Please try a different query.'})
            job['status'] = 'completed'
            with job['condition']:
                job['condition'].notify_all()
            log_event("WARNING", f"No relevant articles found for query '{query}'", "run_background_pipeline", ip=client_ip, perf_ms=(time.time() - start_time) * 1000)
            return

        job['events'].append({'type': 'progress', 'message': 'Generating chronological timeline...'})
        with job['condition']:
            job['condition'].notify_all()

        messages = generate_full_prompt(query, articles)
        message_hash = hashlib.md5(json.dumps(messages, sort_keys=True).encode('utf-8')).hexdigest()
        log_event("INFO", f"Message hash produced: {message_hash}", "run_background_pipeline", ip=client_ip)
        
        llm_start = time.time()
        event_generator = glm_preset_chat(messages)

        for event in event_generator:
            job['events'].append(event)
            with job['condition']:
                job['condition'].notify_all()
            
        job['status'] = 'completed'
        with job['condition']:
            job['condition'].notify_all()
            
        if len(job['events']) < 10:
            log_event("WARNING", f"Timeline generation completed but with very few events ({len(job['events'])}). Query: '{query}'", "run_background_pipeline:glm_preset_chat", ip=client_ip, perf_ms=(time.time() - llm_start) * 1000)
        else:
            log_event("INFO", f"Timeline generation completed successfully, Query: '{query}', Total Events: {len(job['events'])}", "run_background_pipeline:glm_preset_chat", ip=client_ip, perf_ms=(time.time() - llm_start) * 1000)
        log_event("INFO", "Total job completed", "run_background_pipeline", ip=client_ip, perf_ms=(time.time() - start_time) * 1000)

    except Exception as e:
        error_details = traceback.format_exc()
        log_event("ERROR", f"Error during processing: {str(e)}", "run_background_pipeline", ip=client_ip, error=error_details, perf_ms=(time.time() - start_time) * 1000)
        job['events'].append({'type': 'progress', 'message': f'Error during processing: {str(e)}'})
        job['status'] = 'completed'
        with job['condition']:
            job['condition'].notify_all()

# ------------------------------

@app.route('/')
def index():
    client_ip = request.remote_addr
    log_event("INFO", "Accessed homepage", "index", ip=client_ip)
    return render_template('index.html')


@app.route('/api/health')
def health():
    # Simple health check for frontend to confirm backend/retriever is reachable
    client_ip = request.remote_addr
    log_event("INFO", "Health check", "health", ip=client_ip)
    return Response(json.dumps({"ok": True, "service": "retriever"}), mimetype='application/json')

@app.route('/api/news')
def get_news():
    query = request.args.get('query', '')
    query = query.strip()
    client_ip = request.remote_addr
    
    if not query:
        log_event("WARNING", "Empty query received", "get_news", ip=client_ip)
        return Response("event: close\ndata: {}\n\n", mimetype='text/event-stream')

    if len(query) > 100:
        log_event("WARNING", f"Query too long: {len(query)} characters", "get_news", ip=client_ip)
        def reject_stream():
            yield f"data: {json.dumps({'type': 'progress', 'message': 'Query is too long. Please limit to 100 characters.'})}\n\n"
            yield "event: close\ndata: {}\n\n"
        return Response(reject_stream(), mimetype='text/event-stream')


    log_event("INFO", f"Query searched: {query}", "get_news", ip=client_ip)

    # Initialize or attach to an existing background job
    with job_lock:
        if query not in job_store:
            # Check concurrent job limit
            active_jobs = sum(1 for j in job_store.values() if j['status'] == 'running')
            if active_jobs >= MAX_CONCURRENT_JOBS:
                log_event("WARNING", f"Server capacity reached ({active_jobs}/{MAX_CONCURRENT_JOBS}). Rejected query.", "get_news", ip=client_ip)
                def reject_stream():
                    yield f"data: {json.dumps({'type': 'progress', 'message': f'Server is at capacity. Please try again in a moment.'})}\n\n"
                    yield "event: close\ndata: {}\n\n"
                return Response(reject_stream(), mimetype='text/event-stream')

            job_store[query] = {
                'status': 'running',
                'events': [],
                'condition': threading.Condition()
            }
            # Start LLM process totally detached from this HTTP socket
            t = threading.Thread(target=run_background_pipeline, args=(query, job_store[query], client_ip))
            t.daemon = True
            t.start()
        else:
            log_event("INFO", f"Reattached to existing job for query: {query}", "get_news", ip=client_ip)
            
    job = job_store[query]

    def generate():
        yielded_count = 0
        while True:
            events_to_yield = []
            is_done = False
            
            with job['condition']:
                # Wait until there are new events to stream or the job finishes
                while yielded_count >= len(job['events']) and job['status'] == 'running':
                    job['condition'].wait()
                
                # Copy the events to yield so we can release the lock before yielding
                while yielded_count < len(job['events']):
                    events_to_yield.append(job['events'][yielded_count])
                    yielded_count += 1
                
                if job['status'] != 'running' and yielded_count >= len(job['events']):
                    is_done = True
            
            # Yield outside the lock to prevent freezing the background thread!
            for event in events_to_yield:
                yield f"data: {json.dumps(event)}\n\n"
                
            if is_done:
                yield "event: close\ndata: {}\n\n"
                break

    return Response(generate(), mimetype='text/event-stream')

@app.route('/api/feedback', methods=['POST'])
def submit_feedback():
    client_ip = request.remote_addr
    try:
        payload = request.get_json(silent=True) or {}
        record = save_feedback_entry(payload, client_ip, request.headers.get('User-Agent', 'unknown'))
        log_event("INFO", "Feedback submitted", "submit_feedback", ip=client_ip)
        return Response(json.dumps({"ok": True, "record": record}), mimetype='application/json')
    except Exception as e:
        error_details = traceback.format_exc()
        log_event("ERROR", f"Failed to save feedback: {str(e)}", "submit_feedback", ip=client_ip, error=error_details)
        return Response(json.dumps({"ok": False, "error": str(e)}), status=400, mimetype='application/json')

if __name__ == '__main__':
    app.run(debug=True, port=5000, use_reloader=False, host="127.0.0.1")
