import json
import os
import threading
import time
from datetime import datetime, timedelta
from flask import Flask, request, render_template, redirect, url_for, session, flash

# --- Configuration & File Paths ---
QUEUE_FILE = 'queue_data.json'
RUNS_FILE = 'runs_tracker.json'
CONFIG_FILE = 'config.json' 
MAX_CONCURRENT_RUNS = 4  # FIXED MAX SLOTS
DEFAULT_RUN_TIME_SECONDS = 300 

# --- Config Helper Functions ---

def load_config():
    """Loads configuration data, only tracking run_time."""
    if not os.path.exists(CONFIG_FILE):
        return {'run_time': DEFAULT_RUN_TIME_SECONDS}
    try:
        with open(CONFIG_FILE, 'r') as f:
            config = json.load(f)
            if 'run_time' not in config:
                 config['run_time'] = DEFAULT_RUN_TIME_SECONDS
            return config
    except json.JSONDecodeError:
        print(f"Error decoding JSON from {CONFIG_FILE}. Returning default config.")
        return {'run_time': DEFAULT_RUN_TIME_SECONDS}

def save_config(config_data):
    """Writes configuration data to a JSON file."""
    with open(CONFIG_FILE, 'w') as f:
        json.dump(config_data, f, indent=2)

# Load initial configuration
APP_CONFIG = load_config()

# --- 1. Global State Management (Fixed 4 Slots) ---

def initialize_active_runs(max_runs=MAX_CONCURRENT_RUNS):
    """Creates the fixed 4-slot structure with an assigned_run_time field."""
    return {
        str(i): {
            'team_id': None, 
            'start_time': None,       
            'time_spent_sec': 0,      
            'timer_thread': None,     
            'status': 'IDLE',
            'assigned_run_time_sec': DEFAULT_RUN_TIME_SECONDS # Key for run time stability
        } for i in range(1, max_runs + 1)
    }

active_runs = initialize_active_runs()
active_lock = threading.Lock() 

# --- 2. Flask Initialization ---
APP = Flask(__name__) 
APP.secret_key = 'your_super_secret_key_here'


# --- 3. JSON Helper Functions ---

def load_data(filename):
    """Loads JSON data from a file."""
    if not os.path.exists(filename):
        return [] if filename == QUEUE_FILE else {}
    try:
        with open(filename, 'r') as f:
            return json.load(f)
    except json.JSONDecodeError:
        return [] if filename == QUEUE_FILE else {}

def save_data(filename, data):
    """Writes data to a JSON file."""
    with open(filename, 'w') as f:
        json.dump(data, f, indent=2)


# --- 4. Core Timer & Setting Logic ---

def get_current_run_time():
    """Retrieves the current global run time from the session/config."""
    return session.get('run_time', APP_CONFIG['run_time'])

@APP.route('/set_run_time', methods=['POST'])
def set_run_time():
    """Supervisor action: Sets the desired run time globally (will only affect NEW runs)."""
    run_time_minutes = request.form.get('run_time_minutes', '')
    
    try:
        minutes = int(run_time_minutes)
        if minutes > 0:
            new_run_time_seconds = minutes * 60
            
            # Update Session (for immediate use) and Persistent Config
            session['run_time'] = new_run_time_seconds
            config = load_config()
            config['run_time'] = new_run_time_seconds
            save_config(config)
            
            flash(f"Global run time set to {minutes} minutes. **This will only affect runs started from now on.**", "success")
        else:
            flash("Invalid run time entered. Must be greater than 0.", "error")
    except ValueError:
        flash("Invalid input for run time.", "error")
        
    return redirect(url_for('index'))


def cancel_active_timer(slot_id):
    """Helper to safely cancel the currently running timer thread for a specific slot."""
    global active_runs
    
    run_slot = active_runs.get(slot_id)
    if not run_slot:
        return

    if run_slot.get('timer_thread') and run_slot['timer_thread'].is_alive():
        run_slot['timer_thread'].cancel()
        print(f"Existing timer thread for Slot {slot_id} cancelled.")
    run_slot['timer_thread'] = None


def start_run_timer(slot_id, remaining_time_sec):
    """Starts a non-blocking timer thread for the remaining run time."""
    global active_runs
    
    run_slot = active_runs[slot_id]
    cancel_active_timer(slot_id)
    
    def timer_expired():
        """Executed when the run time is up."""
        with active_lock:
            team_id = run_slot.get('team_id')
            if team_id and run_slot['status'] == 'RUNNING':
                
                queue = load_data(QUEUE_FILE)
                review_entry = {
                    'team_id': team_id,
                    'timestamp': datetime.now().isoformat(), 
                    'priority_re_run': False,
                    'status': 'REVIEW'
                }
                
                queue.append(review_entry)
                save_data(QUEUE_FILE, queue)

                # Reset slot to IDLE state
                run_slot.update({
                    'team_id': None, 
                    'start_time': None, 
                    'time_spent_sec': 0, 
                    'timer_thread': None, 
                    'status': 'IDLE',
                    'assigned_run_time_sec': DEFAULT_RUN_TIME_SECONDS # Reset time field
                })
                print(f"Run time expired for {team_id} in Slot {slot_id}. Moved to review.")
            
    timer_thread = threading.Timer(remaining_time_sec, timer_expired)
    timer_thread.daemon = True 
    timer_thread.start()
    
    run_slot['timer_thread'] = timer_thread
    print(f"Timer started for {run_slot.get('team_id', 'Unknown')} in Slot {slot_id} for {remaining_time_sec:.2f} seconds.")


# --- 5. Core Sorting Logic (Same as before) ---

def get_sorted_queue():
    """Loads active queue and run history, then sorts the queue based on priority rules."""
    waiting_queue = load_data(QUEUE_FILE)
    teams_history = load_data(RUNS_FILE)

    def custom_sort_key(entry):
        runs = teams_history.get(entry.get('team_id'), 0)
        
        status = entry.get('status', 'WAITING')
        try:
            timestamp = datetime.fromisoformat(entry.get('timestamp'))
        except (ValueError, TypeError):
            timestamp = datetime.max 
        
        return (
            status != 'REVIEW',
            not entry.get('priority_re_run', False),
            runs,
            timestamp
        )

    return sorted(waiting_queue, key=custom_sort_key)


# --- 6. Flask Web Routes (Display) ---

@APP.route('/')
def index():
    """Renders the main queue page, calculating time remaining using the slot's assigned time."""
    global active_runs
    
    GLOBAL_CONFIG_RUN_TIME = get_current_run_time()
    active_runs_display = {} 
    
    with active_lock:
        for slot_id, slot_data in active_runs.items():
            
            time_remaining = None
            
            # Use the time ASSIGNED to the run when it started.
            assigned_time = slot_data.get('assigned_run_time_sec', DEFAULT_RUN_TIME_SECONDS)
            time_remaining_sec = assigned_time - slot_data['time_spent_sec'] 

            if slot_data['team_id']:
                
                if slot_data['status'] == 'RUNNING':
                    start = datetime.fromisoformat(slot_data['start_time'])
                    elapsed_current_segment = (datetime.now() - start).total_seconds()
                    total_time_spent = slot_data['time_spent_sec'] + elapsed_current_segment
                    time_remaining_sec = assigned_time - total_time_spent 
                    
                    if time_remaining_sec > 0:
                        minutes = int(time_remaining_sec // 60)
                        seconds = int(time_remaining_sec % 60)
                        time_remaining = f"{minutes:02d}:{seconds:02d}"
                    else:
                        time_remaining = "00:00"
                        
                elif slot_data['status'] == 'PAUSED' or slot_data['status'] == 'DYSFUNCTIONAL':
                    if time_remaining_sec > 0:
                        minutes = int(time_remaining_sec // 60)
                        seconds = int(time_remaining_sec % 60)
                        time_remaining = f"{minutes:02d}:{seconds:02d} ({slot_data['status']})"
                    else:
                        time_remaining = "00:00 (EXPIRED)"
            
            active_runs_display[slot_id] = {
                'slot_data': slot_data,
                'time_remaining': time_remaining,
                'time_remaining_sec': max(0, time_remaining_sec)
            }
            
    queue = get_sorted_queue()
    teams_history = load_data(RUNS_FILE)
    
    review_team = next((team for team in queue if team.get('status') == 'REVIEW'), None)
    
    return render_template('index.html', 
                           queue=queue, 
                           teams_history=teams_history,
                           active_runs_display=active_runs_display,
                           MAX_RUNS=MAX_CONCURRENT_RUNS,
                           review_team=review_team,
                           RUN_TIME_SECONDS=GLOBAL_CONFIG_RUN_TIME) 


@APP.route('/join', methods=['POST'])
def join_queue():
    """Adds a team to the waiting queue."""
    team_id = request.form.get('team_id', '').strip()
    
    if not team_id:
        return redirect(url_for('index'))

    queue = load_data(QUEUE_FILE)
    
    if any(entry['team_id'] == team_id for entry in queue):
        flash(f"Team {team_id} is already in the queue or in review.", "error")
        return redirect(url_for('index'))

    with active_lock:
        if any(run['team_id'] == team_id for run in active_runs.values()):
            flash(f"Team {team_id} is currently running in an arena slot.", "error")
            return redirect(url_for('index'))

    new_entry = {
        'team_id': team_id,
        'timestamp': datetime.now().isoformat(), 
        'priority_re_run': False,
        'status': 'WAITING'
    }
    
    queue.append(new_entry)
    save_data(QUEUE_FILE, queue)

    history = load_data(RUNS_FILE)
    if team_id not in history:
        history[team_id] = 0
        save_data(RUNS_FILE, history)
    
    flash(f"Team {team_id} added to the waiting queue.", "success")
    return redirect(url_for('index'))


# --- 7. Flask Web Routes (Supervisor Actions) ---

@APP.route('/start_run', methods=['POST'])
def start_run():
    """Starts the next waiting team in an IDLE slot."""
    global active_runs
    
    slot_id = request.form.get('slot_id')
    
    if not slot_id or slot_id not in active_runs:
        flash("Invalid slot ID provided for start run.", "error")
        return redirect(url_for('index'))

    with active_lock:
        run_slot = active_runs[slot_id]
        if run_slot['team_id'] is not None:
            flash(f"Slot {slot_id} is already in use.", "error")
            return redirect(url_for('index'))

    sorted_queue = get_sorted_queue()
    waiting_team = next((team for team in sorted_queue if team.get('status') == 'WAITING'), None)
    
    if not waiting_team:
        flash("No teams in WAITING state to start a run.", "warning")
        return redirect(url_for('index'))

    queue = load_data(QUEUE_FILE)
    
    try:
        index_to_remove = next(i for i, entry in enumerate(queue) 
                               if entry['team_id'] == waiting_team['team_id'] and entry['timestamp'] == waiting_team['timestamp'])
        
        team_entry_for_timer = queue.pop(index_to_remove)
        save_data(QUEUE_FILE, queue)
    except StopIteration:
        flash(f"Error: Could not find team {waiting_team['team_id']} in queue.", "error")
        return redirect(url_for('index'))

    CURRENT_RUN_TIME = get_current_run_time()

    with active_lock:
        run_slot.update({
            'team_id': team_entry_for_timer['team_id'], 
            'start_time': datetime.now().isoformat(),
            'time_spent_sec': 0,
            'status': 'RUNNING',
            'assigned_run_time_sec': CURRENT_RUN_TIME # Assign current time to the slot
        })
    
    start_run_timer(slot_id, CURRENT_RUN_TIME) 
    flash(f"Run started for {team_entry_for_timer['team_id']} in Slot {slot_id}.", "success")
    return redirect(url_for('index'))


@APP.route('/pause_run', methods=['POST'])
def pause_run():
    """Pauses an active run and saves elapsed time."""
    slot_id = request.form.get('slot_id')
    
    if not slot_id or slot_id not in active_runs:
        return redirect(url_for('index'))

    with active_lock:
        run_slot = active_runs[slot_id]
        if run_slot['status'] == 'RUNNING':
            start = datetime.fromisoformat(run_slot['start_time'])
            elapsed_current_segment = (datetime.now() - start).total_seconds()
            
            run_slot['time_spent_sec'] += elapsed_current_segment
            
            run_slot['status'] = 'PAUSED'
            run_slot['start_time'] = None
            
            cancel_active_timer(slot_id)
            
            flash(f"Run paused for {run_slot['team_id']} in Slot {slot_id}.", "warning")
    return redirect(url_for('index'))


@APP.route('/resume_run', methods=['POST'])
def resume_run():
    """Resumes a paused or dysfunctional run."""
    slot_id = request.form.get('slot_id')
    
    if not slot_id or slot_id not in active_runs:
        return redirect(url_for('index'))

    with active_lock:
        run_slot = active_runs[slot_id]
        if run_slot['team_id'] and (run_slot['status'] == 'PAUSED' or run_slot['status'] == 'DYSFUNCTIONAL'):
            
            # Use the time assigned to the slot when the run started
            assigned_time = run_slot.get('assigned_run_time_sec', DEFAULT_RUN_TIME_SECONDS)
            remaining_time = assigned_time - run_slot['time_spent_sec']
            
            if remaining_time > 0:
                run_slot['status'] = 'RUNNING'
                run_slot['start_time'] = datetime.now().isoformat()
                
                start_run_timer(slot_id, remaining_time) 
                
                flash(f"Run resumed for {run_slot['team_id']} in Slot {slot_id}.", "success")
            else:
                flash(f"Cannot resume run for {run_slot['team_id']}; time expired.", "error")
    return redirect(url_for('index'))


@APP.route('/mark_dysfunctional', methods=['POST'])
def mark_dysfunctional():
    """Marks a run as dysfunctional, pausing the timer and saving elapsed time."""
    slot_id = request.form.get('slot_id')
    
    if not slot_id or slot_id not in active_runs:
        return redirect(url_for('index'))

    with active_lock:
        run_slot = active_runs[slot_id]
        if run_slot['status'] == 'RUNNING':
            start = datetime.fromisoformat(run_slot['start_time'])
            elapsed_current_segment = (datetime.now() - start).total_seconds()
            run_slot['time_spent_sec'] += elapsed_current_segment
            cancel_active_timer(slot_id)
            
        if run_slot['team_id']: 
            run_slot['status'] = 'DYSFUNCTIONAL'
            run_slot['start_time'] = None
            flash(f"Run for {run_slot['team_id']} in Slot {slot_id} marked as DYSFUNCTIONAL.", "error")
    return redirect(url_for('index'))


@APP.route('/end_run', methods=['POST'])
def end_run():
    """Completely cancels a run, resetting the slot to IDLE."""
    slot_id = request.form.get('slot_id')
    
    if not slot_id or slot_id not in active_runs:
        return redirect(url_for('index'))
        
    with active_lock:
        run_slot = active_runs[slot_id]
        if run_slot['team_id'] is not None:
            team_id = run_slot['team_id']
            cancel_active_timer(slot_id)
            
            run_slot.update({
                'team_id': None, 
                'start_time': None, 
                'time_spent_sec': 0, 
                'timer_thread': None, 
                'status': 'IDLE',
                'assigned_run_time_sec': DEFAULT_RUN_TIME_SECONDS # Reset time field
            })
            flash(f"Run for {team_id} in Slot {slot_id} completely CANCELED.", "warning")
            
    return redirect(url_for('index'))


@APP.route('/mark_success', methods=['POST'])
def mark_success():
    """Marks the current review team as successful, increments run count, and removes from queue."""
    queue = load_data(QUEUE_FILE)
    review_team_index = next((i for i, team in enumerate(queue) if team.get('status') == 'REVIEW'), -1)

    if review_team_index == -1:
        flash("No team in review state to mark as successful.", "error")
        return redirect(url_for('index'))

    review_team = queue.pop(review_team_index)
    save_data(QUEUE_FILE, queue)

    history = load_data(RUNS_FILE)
    team_id = review_team['team_id']
    history[team_id] = history.get(team_id, 0) + 1 
    save_data(RUNS_FILE, history)
    
    flash(f"Team {team_id} successfully completed run. Total runs: {history[team_id]}.", "success")
    return redirect(url_for('index'))


@APP.route('/mark_failure', methods=['POST'])
def mark_failure():
    """Marks the current review team as a failure, giving them priority for a re-run."""
    queue = load_data(QUEUE_FILE)
    review_team_index = next((i for i, team in enumerate(queue) if team.get('status') == 'REVIEW'), -1)

    if review_team_index == -1:
        flash("No team in review state to mark as failure.", "error")
        return redirect(url_for('index'))

    team = queue[review_team_index]
    team['status'] = 'WAITING'
    team['priority_re_run'] = True
    
    save_data(QUEUE_FILE, queue)
    
    flash(f"Team {team['team_id']} marked for priority re-run.", "warning")
    return redirect(url_for('index'))


# --- 8. Run the Application ---

if __name__ == '__main__':
    # Cleanup: Ensure all REVIEW teams are returned to WAITING on startup
    queue = load_data(QUEUE_FILE)
    changes_made = False
    for team in queue:
        if team.get('status') == 'REVIEW' or 'status' not in team:
            team['status'] = 'WAITING'
            changes_made = True
            
        if 'priority_re_run' not in team:
            team['priority_re_run'] = False
            changes_made = True

    if changes_made:
        save_data(QUEUE_FILE, queue)

    # Initialize run_time in the session if not present (using config value)
    with APP.test_request_context('/'):
        if 'run_time' not in session:
            session['run_time'] = APP_CONFIG['run_time']

    # Start the application
    APP.run(debug=True, host='0.0.0.0', port=5000)