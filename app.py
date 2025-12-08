import json
import os
import threading
import time
from datetime import datetime, timedelta
from flask import Flask, request, render_template, redirect, url_for

# --- Configuration ---
QUEUE_FILE = 'queue_data.json'
RUNS_FILE = 'runs_tracker.json'

# Run time in seconds (e.g., 5 minutes for testing)
RUN_TIME_SECONDS = 300 

# --- 1. Global State Management (Protected by a Lock) ---
# Status: IDLE, RUNNING, PAUSED, DYSFUNCTIONAL
active_run = {
    'team_id': None, 
    'start_time': None,       # Time run started or was last resumed
    'time_spent_sec': 0,      # Total seconds spent running so far
    'timer_thread': None,     # To hold the reference to the running timer
    'status': 'IDLE'          
}
active_lock = threading.Lock() 


# --- 2. Flask Initialization ---
APP = Flask(__name__) 


# --- 3. JSON Helper Functions ---

def load_data(filename):
    """Loads JSON data from a file, returning an empty dict/list if the file doesn't exist."""
    if not os.path.exists(filename):
        if filename == RUNS_FILE:
            return {}
        return []
    
    try:
        with open(filename, 'r') as f:
            return json.load(f)
    except json.JSONDecodeError:
        print(f"Error decoding JSON from {filename}. Returning empty structure.")
        return {} if filename == RUNS_FILE else []

def save_data(filename, data):
    """Writes data to a JSON file."""
    with open(filename, 'w') as f:
        json.dump(data, f, indent=2)


# --- 4. Core Timer Logic ---

def cancel_active_timer():
    """Helper to safely cancel the currently running timer thread."""
    global active_run
    # Check if a timer thread exists and is still active before trying to cancel
    if active_run.get('timer_thread') and active_run['timer_thread'].is_alive():
        active_run['timer_thread'].cancel()
        print("Existing timer thread cancelled.")
    # Clear the reference regardless of cancel success
    active_run['timer_thread'] = None


def start_run_timer(remaining_time_sec):
    """Starts a non-blocking timer thread for the remaining run time."""
    global active_run
    
    # 1. Ensure any old timer is cancelled before starting a new one
    cancel_active_timer()
    
    def timer_expired():
        """Executed when the run time is up."""
        with active_lock:
            team_id = active_run.get('team_id')
            # Only proceed if the run is still active (not paused/ended externally)
            if team_id and active_run['status'] == 'RUNNING':
                
                # Load the current queue list
                queue = load_data(QUEUE_FILE)
                
                # Create a new entry for the team in REVIEW status
                review_entry = {
                    'team_id': team_id,
                    'timestamp': datetime.now().isoformat(), 
                    'priority_re_run': False,
                    'status': 'REVIEW'
                }
                
                queue.append(review_entry)
                save_data(QUEUE_FILE, queue)

                # Clear the active slot and reset timer state
                active_run.update({'team_id': None, 'start_time': None, 'time_spent_sec': 0, 'timer_thread': None, 'status': 'IDLE'})
                print(f"Run time expired for {team_id}. Moved to review.")
            
    # Start the timer thread
    timer_thread = threading.Timer(remaining_time_sec, timer_expired)
    timer_thread.daemon = True 
    timer_thread.start()
    
    active_run['timer_thread'] = timer_thread
    print(f"Timer started for {active_run['team_id']} for {remaining_time_sec:.2f} seconds.")


# --- 5. Core Sorting Logic ---

def get_sorted_queue():
    """
    Loads active queue and run history, then sorts the queue based on priority rules.
    """
    waiting_queue = load_data(QUEUE_FILE)
    teams_history = load_data(RUNS_FILE)

    def custom_sort_key(entry):
        runs = teams_history.get(entry.get('team_id'), 0)
        
        # Ensure 'status' and 'timestamp' exist for reliable sorting
        status = entry.get('status', 'WAITING')
        try:
            timestamp = datetime.fromisoformat(entry.get('timestamp'))
        except (ValueError, TypeError):
            # Fallback for missing or malformed timestamp
            timestamp = datetime.max 
        
        # Priority 1: Review status (REVIEW sorts as 0, WAITING sorts as 1)
        # Priority 2: Technical Re-run 
        # Priority 3: Total Runs Completed 
        # Priority 4: Timestamp (tie-breaker)
        return (
            status != 'REVIEW',
            not entry.get('priority_re_run', False),
            runs,
            timestamp
        )

    return sorted(waiting_queue, key=custom_sort_key)


# --- 6. Flask Web Routes (Student/Display) ---

@APP.route('/')
def index():
    """Renders the main queue page, calculating time remaining for the active run."""
    
    time_remaining = None
    
    with active_lock:
        team_id = active_run['team_id']
        status = active_run['status']
        time_spent_sec = active_run['time_spent_sec']
        start_time_iso = active_run['start_time']
        
        # Default remaining time is the full time
        time_remaining_sec = RUN_TIME_SECONDS - time_spent_sec

        if team_id:
            if status == 'RUNNING':
                # 1. Calculate time spent in the current active segment
                start = datetime.fromisoformat(start_time_iso)
                elapsed_current_segment = (datetime.now() - start).total_seconds()
                
                # 2. Total time run so far (used for display, not saving yet)
                total_time_spent = time_spent_sec + elapsed_current_segment
                
                # 3. Remaining time based on total time run
                time_remaining_sec = RUN_TIME_SECONDS - total_time_spent
                
                if time_remaining_sec > 0:
                    minutes = int(time_remaining_sec // 60)
                    seconds = int(time_remaining_sec % 60)
                    time_remaining = f"{minutes:02d}:{seconds:02d}"
                else:
                    time_remaining = "00:00"
                    
            elif status == 'PAUSED' or status == 'DYSFUNCTIONAL':
                # When paused or dysfunctional, remaining time is static based on saved time_spent_sec
                if time_remaining_sec > 0:
                    minutes = int(time_remaining_sec // 60)
                    seconds = int(time_remaining_sec % 60)
                    time_remaining = f"{minutes:02d}:{seconds:02d} ({status})"
                else:
                    time_remaining = "00:00 (EXPIRED)"
                
    queue = get_sorted_queue()
    teams_history = load_data(RUNS_FILE)
    
    review_team = next((team for team in queue if team.get('status') == 'REVIEW'), None)
    
    # THE FIX: We pass the global constant RUN_TIME_SECONDS into the template context
    return render_template('index.html', 
                           queue=queue, 
                           teams_history=teams_history,
                           active_run=active_run, # Pass the full structure
                           time_remaining=time_remaining,
                           time_remaining_sec=time_remaining_sec,
                           review_team=review_team,
                           RUN_TIME_SECONDS=RUN_TIME_SECONDS) 

@APP.route('/join', methods=['POST'])
def join_queue():
    """Handles a student's request to join the queue."""
    team_id = request.form.get('team_id', '').strip()
    
    if not team_id:
        return redirect(url_for('index'))

    queue = load_data(QUEUE_FILE)
    
    # Check if the team is already waiting OR in review
    if any(entry['team_id'] == team_id for entry in queue):
        return redirect(url_for('index'))

    # Check if the team is currently active
    with active_lock:
        if active_run['team_id'] == team_id:
            return redirect(url_for('index'))

    # Create the new queue entry
    new_entry = {
        'team_id': team_id,
        'timestamp': datetime.now().isoformat(), 
        'priority_re_run': False,
        'status': 'WAITING'
    }
    
    queue.append(new_entry)
    save_data(QUEUE_FILE, queue)

    # Ensure the team exists in the permanent history, initializing to 0 if new
    history = load_data(RUNS_FILE)
    if team_id not in history:
        history[team_id] = 0
        save_data(RUNS_FILE, history)

    return redirect(url_for('index'))


# --- 7. Flask Web Routes (Supervisor Actions) ---

@APP.route('/start_run', methods=['POST'])
def start_run():
    """
    Supervisor action: Moves the top team from WAITING to ACTIVE state and starts the timer.
    """
    global active_run
    
    with active_lock:
        # 1. Check if the arena is already in use
        if active_run['team_id'] is not None:
            return redirect(url_for('index'))

    sorted_queue = get_sorted_queue()
    
    # Filter out teams in REVIEW state, as they cannot start a run
    waiting_team = next((team for team in sorted_queue if team.get('status') == 'WAITING'), None)
    
    if not waiting_team:
        print("No teams in WAITING state to start a run.")
        return redirect(url_for('index'))

    # --- Step 2: Remove from Active Queue ---
    queue = load_data(QUEUE_FILE)
    
    try:
        # Find the specific entry that was at the top of the WAITING list based on team_id and timestamp
        index_to_remove = next(i for i, entry in enumerate(queue) 
                               if entry['team_id'] == waiting_team['team_id'] and entry['timestamp'] == waiting_team['timestamp'])
        
        # We need the full entry for the timer, so we pop it and use it
        team_entry_for_timer = queue.pop(index_to_remove)
        save_data(QUEUE_FILE, queue)
    except StopIteration:
        print(f"Error: Could not find team {waiting_team['team_id']} in queue to start run.")
        return redirect(url_for('index'))

    # 3. Assign team to the active slot and start timer
    with active_lock:
        active_run.update({
            'team_id': team_entry_for_timer['team_id'], 
            'start_time': datetime.now().isoformat(),
            'time_spent_sec': 0, # Reset time spent for a new run
            'status': 'RUNNING' 
        })
    
    # Start timer for the full run time
    start_run_timer(RUN_TIME_SECONDS) 
    print(f"Run started for {team_entry_for_timer['team_id']}")
    return redirect(url_for('index'))


@APP.route('/pause_run', methods=['POST'])
def pause_run():
    """Supervisor action: Pauses the active run."""
    with active_lock:
        if active_run['status'] == 'RUNNING':
            # 1. Calculate time spent in the segment that just finished
            start = datetime.fromisoformat(active_run['start_time'])
            elapsed_current_segment = (datetime.now() - start).total_seconds()
            
            # 2. Add to total time spent
            active_run['time_spent_sec'] += elapsed_current_segment
            
            # 3. Update status and clear start time
            active_run['status'] = 'PAUSED'
            active_run['start_time'] = None
            
            # 4. Cancel the active timer thread
            cancel_active_timer()
            
            print(f"Run paused for {active_run['team_id']}. Total time spent: {active_run['time_spent_sec']:.2f}s")
    return redirect(url_for('index'))


@APP.route('/resume_run', methods=['POST'])
def resume_run():
    """Supervisor action: Resumes a paused or dysfunctional run."""
    with active_lock:
        if active_run['team_id'] and (active_run['status'] == 'PAUSED' or active_run['status'] == 'DYSFUNCTIONAL'):
            remaining_time = RUN_TIME_SECONDS - active_run['time_spent_sec']
            
            if remaining_time > 0:
                # 1. Update status and set new start time
                active_run['status'] = 'RUNNING'
                active_run['start_time'] = datetime.now().isoformat()
                
                # 2. Restart timer for remaining time
                start_run_timer(remaining_time) 
                
                print(f"Run resumed for {active_run['team_id']} for remaining {remaining_time:.2f}s")
            else:
                print("Cannot resume run; time expired.")
    return redirect(url_for('index'))


@APP.route('/mark_dysfunctional', methods=['POST'])
def mark_dysfunctional():
    """Supervisor action: Marks the run as dysfunctional (like a permanent pause for analysis)."""
    with active_lock:
        if active_run['status'] == 'RUNNING':
            # If running, we need to save the time spent first (same logic as pause)
            start = datetime.fromisoformat(active_run['start_time'])
            elapsed_current_segment = (datetime.now() - start).total_seconds()
            active_run['time_spent_sec'] += elapsed_current_segment
            cancel_active_timer()
            
        if active_run['team_id']: 
            active_run['status'] = 'DYSFUNCTIONAL'
            active_run['start_time'] = None
            print(f"Run marked as DYSFUNCTIONAL for {active_run['team_id']}. Total time spent: {active_run['time_spent_sec']:.2f}s")
    return redirect(url_for('index'))


@APP.route('/end_run', methods=['POST'])
def end_run():
    """Supervisor action: Immediately ends and cancels the active run without recording results or review."""
    with active_lock:
        if active_run['team_id'] is not None:
            team_id = active_run['team_id']
            cancel_active_timer()
            
            # Reset the active slot completely
            active_run.update({'team_id': None, 'start_time': None, 'time_spent_sec': 0, 'timer_thread': None, 'status': 'IDLE'})
            print(f"Run canceled for {team_id}.")
            
    return redirect(url_for('index'))


@APP.route('/mark_success', methods=['POST'])
def mark_success():
    """
    Supervisor action: Handles team in REVIEW state as SUCCESSFUL.
    1. Removes team from queue_data.json.
    2. Increments run count in runs_tracker.json.
    """
    # 1. Find the team in REVIEW state (we only look for the first one, as they are highest priority)
    queue = load_data(QUEUE_FILE)
    review_team_index = next((i for i, team in enumerate(queue) if team.get('status') == 'REVIEW'), -1)

    if review_team_index == -1:
        print("No team in review state to mark as successful.")
        return redirect(url_for('index'))

    review_team = queue.pop(review_team_index)
    save_data(QUEUE_FILE, queue)

    # 2. Update Run Count in History
    history = load_data(RUNS_FILE)
    team_id = review_team['team_id']
    history[team_id] = history.get(team_id, 0) + 1 
    save_data(RUNS_FILE, history)
    
    print(f"Team {team_id} successfully completed run. Total runs: {history[team_id]}")
    return redirect(url_for('index'))


@APP.route('/mark_failure', methods=['POST'])
def mark_failure():
    """
    Supervisor action: Handles team in REVIEW state as TECHNICAL FAILURE.
    1. Updates the team's status to WAITING and sets 'priority_re_run' to True.
    2. DOES NOT increment run count.
    """
    # 1. Find the team in REVIEW state
    queue = load_data(QUEUE_FILE)
    review_team_index = next((i for i, team in enumerate(queue) if team.get('status') == 'REVIEW'), -1)

    if review_team_index == -1:
        print("No team in review state to mark as failure.")
        return redirect(url_for('index'))

    # 2. Update the existing entry
    team = queue[review_team_index]
    team['status'] = 'WAITING'
    team['priority_re_run'] = True
    # Crucially, the timestamp should NOT be updated, so they maintain their original position priority
    
    save_data(QUEUE_FILE, queue)
    
    print(f"Team {team['team_id']} marked for priority re-run due to failure.")
    # No need to update runs_tracker.json
    return redirect(url_for('index'))


# --- 8. Run the Application ---

if __name__ == '__main__':
    # CRITICAL FIX: Ensure all queue entries have the necessary keys for reliable operation,
    # and clear any REVIEW status from a crash.
    queue = load_data(QUEUE_FILE)
    changes_made = False
    for team in queue:
        # 1. Ensure 'status' exists and clear 'REVIEW' status
        if team.get('status') == 'REVIEW' or 'status' not in team:
            team['status'] = 'WAITING'
            changes_made = True
            
        # 2. Ensure 'priority_re_run' exists
        if 'priority_re_run' not in team:
            team['priority_re_run'] = False
            changes_made = True

    if changes_made:
        save_data(QUEUE_FILE, queue)

    # host='0.0.0.0' allows access from other devices on the network
    # debug=True allows for automatic reloading on code changes
    APP.run(debug=True, host='0.0.0.0', port=5000)