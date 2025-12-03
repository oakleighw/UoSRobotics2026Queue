import json
import os
from datetime import datetime
from flask import Flask, request, render_template, redirect, url_for

# --- Configuration ---
QUEUE_FILE = 'queue_data.json'
RUNS_FILE = 'runs_tracker.json'

# --- 1. Flask Initialization ---
# Initialize the Flask application
APP = Flask(__name__) 


# --- 2. JSON Helper Functions ---

def load_data(filename):
    """Loads JSON data from a file, returning an empty dict/list if the file doesn't exist."""
    if not os.path.exists(filename):
        # Return an appropriate empty container based on the file's known structure
        if filename == RUNS_FILE:
            return {}
        return []
    
    try:
        with open(filename, 'r') as f:
            return json.load(f)
    except json.JSONDecodeError:
        print(f"Error decoding JSON from {filename}. Returning empty structure.")
        # Handles cases where file might be empty or corrupted
        return {} if filename == RUNS_FILE else []

def save_data(filename, data):
    """Writes data to a JSON file."""
    with open(filename, 'w') as f:
        # Use indent=2 for human-readable formatting
        json.dump(data, f, indent=2)


# --- 3. Core Sorting Logic ---

def get_sorted_queue():
    """
    Loads active queue and run history, then sorts the queue based on priority rules:
    1. priority_re_run (True)
    2. Total Runs Completed (Lowest first)
    3. Timestamp (Earliest first)
    """
    waiting_queue = load_data(QUEUE_FILE)
    teams_history = load_data(RUNS_FILE)

    def custom_sort_key(entry):
        # 1. Get the run count for the team from the permanent history (default to 0)
        runs = teams_history.get(entry['team_id'], 0)
        
        # 2. Convert ISO timestamp string to a datetime object for accurate comparison
        try:
            timestamp = datetime.fromisoformat(entry['timestamp'])
        except ValueError:
            # Fallback for bad data: assign max time to push it to the end
            timestamp = datetime.max 

        return (
            # Priority 1: Technical Re-run (False sorts as 1, True sorts as 0)
            not entry.get('priority_re_run', False),
            
            # Priority 2: Total Runs Completed (Lowest number sorts first)
            runs,
            
            # Priority 3: Timestamp (Earliest time sorts first)
            timestamp
        )

    return sorted(waiting_queue, key=custom_sort_key)


# --- 4. Flask Web Routes (Student/Display) ---

@APP.route('/')
def index():
    """Renders the main queue page."""
    # The sorted queue is retrieved and passed to the template
    queue = get_sorted_queue()
    # Also pass the full team history for display purposes (e.g., in a supervisor section)
    teams_history = load_data(RUNS_FILE)
    
    # We assume 'index.html' is in a 'templates' folder
    return render_template('index.html', queue=queue, teams_history=teams_history)

@APP.route('/join', methods=['POST'])
def join_queue():
    """Handles a student's request to join the queue."""
    team_id = request.form.get('team_id', '').strip()
    
    if not team_id:
        # Simple validation
        return redirect(url_for('index'))

    queue = load_data(QUEUE_FILE)
    
    # Check if the team is already waiting
    if any(entry['team_id'] == team_id for entry in queue):
        # Already waiting, just redirect
        return redirect(url_for('index'))

    # Create the new queue entry
    new_entry = {
        'team_id': team_id,
        'timestamp': datetime.now().isoformat(), 
        'priority_re_run': False 
    }
    
    # Add the new entry and save the updated queue file
    queue.append(new_entry)
    save_data(QUEUE_FILE, queue)

    # Ensure the team exists in the permanent history, initializing to 0 if new
    history = load_data(RUNS_FILE)
    if team_id not in history:
        history[team_id] = 0
        save_data(RUNS_FILE, history)

    return redirect(url_for('index'))


# --- 5. Flask Web Routes (Supervisor Actions) ---

@APP.route('/next_team', methods=['POST'])
def next_team():
    """
    Marks the top team's run as SUCCESSFUL.
    1. Removes team from queue_data.json.
    2. Increments run count in runs_tracker.json.
    """
    sorted_queue = get_sorted_queue()
    if not sorted_queue:
        return redirect(url_for('index'))

    # Get the top team (the one currently running)
    completed_team = sorted_queue[0]
    team_id = completed_team['team_id']

    # --- Step 1: Remove from Active Queue ---
    # Load the UNSORTED queue (easier to remove by comparing list items)
    queue = load_data(QUEUE_FILE)
    
    # Find and remove the matching entry from the queue list
    # Note: Because multiple entries *could* exist for one ID (bad practice, but safety measure), 
    # we match by timestamp to remove the specific entry that was at the top.
    try:
        # Find the first item in the queue that matches both ID and original timestamp
        index_to_remove = next(i for i, entry in enumerate(queue) 
                               if entry['team_id'] == team_id and entry['timestamp'] == completed_team['timestamp'])
        queue.pop(index_to_remove)
        save_data(QUEUE_FILE, queue)
    except StopIteration:
        # Should not happen if data is consistent
        print(f"Error: Could not find team {team_id} in queue to remove.")


    # --- Step 2: Update Run Count in History ---
    history = load_data(RUNS_FILE)
    # Use .get() with a default of 0 in case the team is somehow new
    history[team_id] = history.get(team_id, 0) + 1 
    save_data(RUNS_FILE, history)
    
    print(f"Team {team_id} successfully completed a run. Total runs: {history[team_id]}")
    return redirect(url_for('index'))


@APP.route('/fail_rerun', methods=['POST'])
def fail_rerun():
    """
    Marks the top team's run as a TECHNICAL FAILURE.
    1. Updates the team's entry in the queue to set 'priority_re_run' to True.
    2. DOES NOT increment run count in runs_tracker.json.
    """
    sorted_queue = get_sorted_queue()
    if not sorted_queue:
        return redirect(url_for('index'))

    # Get the top team (the one currently running)
    failed_team = sorted_queue[0]
    team_id = failed_team['team_id']

    # --- Step 1: Update Active Queue Entry ---
    # Load the UNSORTED queue
    queue = load_data(QUEUE_FILE)

    # Find and update the specific entry that was at the top
    try:
        for entry in queue:
            # Match by both ID and original timestamp
            if entry['team_id'] == team_id and entry['timestamp'] == failed_team['timestamp']:
                entry['priority_re_run'] = True
                print(f"Team {team_id} marked for priority re-run.")
                break
        
        save_data(QUEUE_FILE, queue)

    except Exception as e:
        print(f"Error marking team {team_id} for re-run: {e}")

    # No need to update runs_tracker.json

    return redirect(url_for('index'))


# --- 6. Run the Application ---

if __name__ == '__main__':
    # host='0.0.0.0' makes the server accessible on the local network (for student phones/laptops)
    # debug=True allows for automatic reloading on code changes
    APP.run(debug=True, host='0.0.0.0', port=5000)