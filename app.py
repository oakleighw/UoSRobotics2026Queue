from flask import Flask, render_template, request, redirect, url_for, flash
import time
from datetime import datetime, timedelta

app = Flask(__name__)
app.secret_key = 'supersecretkey'

# Global State
queue = []
active_runs = {
    1: {'team_id': None, 'start_time': None, 'status': 'IDLE', 'time_paused_at': None, 'time_remaining': None},
    2: {'team_id': None, 'start_time': None, 'status': 'IDLE', 'time_paused_at': None, 'time_remaining': None},
    3: {'team_id': None, 'start_time': None, 'status': 'IDLE', 'time_paused_at': None, 'time_remaining': None},
    4: {'team_id': None, 'start_time': None, 'status': 'IDLE', 'time_paused_at': None, 'time_remaining': None},
}
# Default run time is 5 minutes (300 seconds)
RUN_TIME_SECONDS = 300 
teams_history = {} # {'TEAM_A': 2, 'TEAM_B': 1}

# --- Helper Functions for Time and Display ---

def get_time_remaining(run_data):
    """Calculates the time remaining for a run."""
    if run_data['status'] == 'IDLE':
        return 0
    if run_data['status'] == 'PAUSED' or run_data['status'] == 'DYSFUNCTIONAL':
        return run_data['time_remaining']
    
    # Calculate time passed
    elapsed_time = time.time() - run_data['start_time']
    
    # Calculate remaining time
    remaining = max(0, RUN_TIME_SECONDS - elapsed_time)
    
    # If time runs out, automatically move to REVIEW (This is a simplified automation)
    if remaining == 0:
        team_id = run_data['team_id']
        slot_id = next(id for id, data in active_runs.items() if data['team_id'] == team_id)
        
        # Mark the run for review
        team_index = next((i for i, item in enumerate(queue) if item['team_id'] == team_id and item['status'] == 'RUNNING'), None)
        if team_index is not None:
            queue[team_index]['status'] = 'REVIEW'
            # Ensure non-priority runs don't clear the flag if they time out
            if not queue[team_index]['priority_re_run']:
                 queue[team_index]['priority_re_run'] = False
        
        # Clear the active slot
        active_runs[slot_id] = {'team_id': None, 'start_time': None, 'status': 'IDLE', 'time_paused_at': None, 'time_remaining': None}
        flash(f'Team {team_id} run has ended (time out) and moved to REVIEW Queue!', 'warning')
        return 0

    return remaining

def format_seconds(seconds):
    """Formats seconds into MM:SS string."""
    minutes = int(seconds // 60)
    seconds = int(seconds % 60)
    return f"{minutes:02d}:{seconds:02d}"

# --- NEW PRIORITY SORTING FUNCTION ---

def sort_waiting_queue_priority(queue_list, history):
    """
    Sorts the waiting queue based on the new custom rules:
    1. Highest Priority (Tier 1): Teams with 0 total successful runs.
    2. Secondary Priority (Tier 2): Teams with priority_re_run == True (Dysfunctional re-run).
    3. Tertiary Priority (Tier 3): All other teams, sorted by lowest run count.
    
    FIFO (original index) is used as a tie-breaker within each tier.
    """
    
    # Separate the WAITING teams
    waiting_teams = [team for team in queue_list if team['status'] == 'WAITING']
    
    def get_sort_key(team):
        team_id = team['team_id']
        run_count = history.get(team_id, 0)
        is_priority = team.get('priority_re_run', False)
        
        # We use the team's original index as a final tie-breaker (FIFO)
        fifo_index = queue_list.index(team)
        
        # --- TIER DETERMINATION ---
        
        # Tier 1 (0): Zero-run teams (Highest priority)
        if run_count == 0:
            return (0, run_count, fifo_index) # run_count is 0 here
        
        # Tier 2 (1): Dysfunctional Re-run teams (Second highest priority)
        elif is_priority:
            return (1, run_count, fifo_index)
            
        # Tier 3 (2): Standard teams (Lowest priority)
        else:
            # Within Tier 3, we still sort by lowest run count first
            return (2, run_count, fifo_index) 

    # Sort the waiting teams using the custom key
    sorted_waiting_teams = sorted(waiting_teams, key=get_sort_key)
    
    return sorted_waiting_teams

def get_next_team_in_queue():
    """Returns the team_id of the next team to run based on the new priority logic."""
    # We must sort the list based on the new rules before picking the first one
    sorted_waiting = sort_waiting_queue_priority(queue, teams_history)
    
    if sorted_waiting:
        return sorted_waiting[0]['team_id']
    return None

# --- Flask Routes ---

@app.route('/')
def index():
    # 1. Update/Clean up active runs and calculate remaining time
    active_runs_display = {}
    next_waiting_team_id = get_next_team_in_queue()

    for slot_id, data in active_runs.items():
        if data['status'] != 'IDLE':
            time_rem = get_time_remaining(data)
            data['time_remaining'] = time_rem # Update remaining time for paused/dysfunctional slots
            active_runs_display[slot_id] = {
                'slot_data': data,
                'time_remaining_sec': int(time_rem),
                'time_remaining': format_seconds(time_rem)
            }
        else:
            active_runs_display[slot_id] = {
                'slot_data': data,
                'time_remaining_sec': 0,
                'time_remaining': '00:00'
            }
            
    # 2. Re-sort the queue list for display using the new function
    # NOTE: The *main* queue list `queue` is *not* permanently re-ordered here,
    # only the WAITING subset of teams is sorted for display/selection.
    # We create a temporary list to send to the template:
    display_queue = [team for team in queue if team['status'] != 'WAITING']
    display_queue.extend(sort_waiting_queue_priority(queue, teams_history))


    # 3. Get the *actual* next team object for the idle slot buttons
    next_waiting_team = next((team for team in display_queue if team['team_id'] == next_waiting_team_id), None)

    return render_template('index.html', 
                           queue=display_queue, # Use the sorted list for display
                           active_runs_display=active_runs_display, 
                           next_waiting_team=next_waiting_team, # This is used by the IDLE slot button
                           RUN_TIME_SECONDS=RUN_TIME_SECONDS,
                           teams_history=teams_history)

@app.route('/join_queue', methods=['POST'])
def join_queue():
    team_id = request.form['team_id'].upper().strip()
    
    if not team_id:
        flash('Team ID cannot be empty.', 'error')
        return redirect(url_for('index'))
        
    # Check if the team is already running or waiting
    if any(item['team_id'] == team_id and item['status'] in ('WAITING', 'RUNNING') for item in queue):
        flash(f'Team {team_id} is already in the queue or currently running.', 'warning')
        return redirect(url_for('index'))
    
    # Add new team to the queue with default status
    queue.append({
        'team_id': team_id,
        'status': 'WAITING',
        'priority_re_run': False, # New teams start with no priority
        'time_added': time.time()
    })
    flash(f'Team {team_id} added to the waiting queue.', 'success')
    return redirect(url_for('index'))

@app.route('/start_run', methods=['POST'])
def start_run():
    slot_id = int(request.form['slot_id'])
    
    # Get the next team according to the *new* priority logic
    team_id_to_start = get_next_team_in_queue()
    
    if not team_id_to_start:
        flash('Cannot start run: Waiting queue is empty.', 'error')
        return redirect(url_for('index'))

    if active_runs[slot_id]['status'] != 'IDLE':
        flash(f'Slot {slot_id} is not idle.', 'error')
        return redirect(url_for('index'))

    # 1. Update the active run slot
    active_runs[slot_id] = {
        'team_id': team_id_to_start,
        'start_time': time.time(),
        'status': 'RUNNING',
        'time_paused_at': None,
        'time_remaining': RUN_TIME_SECONDS
    }

    # 2. Update the team's status in the queue from WAITING to RUNNING
    team_index = next((i for i, item in enumerate(queue) if item['team_id'] == team_id_to_start and item['status'] == 'WAITING'), None)
    if team_index is not None:
        queue[team_index]['status'] = 'RUNNING'
        flash(f'Team {team_id_to_start} started run in Slot {slot_id}.', 'success')
    else:
        # Should not happen if get_next_team_in_queue is correct
        flash(f'Error: Could not find {team_id_to_start} in the WAITING queue.', 'error')
        
    return redirect(url_for('index'))


@app.route('/start_session', methods=['POST'])
#If  waiting time > time left in session, block further queue adds or warn.


@app.route('/pause_run', methods=['POST'])
def pause_run():
    slot_id = int(request.form['slot_id'])
    run_data = active_runs.get(slot_id)
    
    if run_data and run_data['status'] == 'RUNNING':
        # Calculate and store remaining time
        time_rem = get_time_remaining(run_data)
        run_data.update({
            'status': 'PAUSED',
            'time_paused_at': time.time(),
            'time_remaining': time_rem
        })
        # Update the corresponding queue item
        team_index = next((i for i, item in enumerate(queue) if item['team_id'] == run_data['team_id'] and item['status'] == 'RUNNING'), None)
        if team_index is not None:
            queue[team_index]['status'] = 'PAUSED'
            flash(f'Team {run_data["team_id"]} run in Slot {slot_id} has been PAUSED.', 'warning')
    else:
        flash(f'Slot {slot_id} is not running.', 'error')
    return redirect(url_for('index'))

@app.route('/resume_run', methods=['POST'])
def resume_run():
    slot_id = int(request.form['slot_id'])
    run_data = active_runs.get(slot_id)
    
    if run_data and run_data['status'] in ('PAUSED', 'DYSFUNCTIONAL'):
        time_rem = run_data['time_remaining']
        run_data.update({
            'start_time': time.time() - (RUN_TIME_SECONDS - time_rem), # Adjust start_time to reflect time already used
            'status': 'RUNNING',
            'time_paused_at': None,
        })
        # Update the corresponding queue item
        team_index = next((i for i, item in enumerate(queue) if item['team_id'] == run_data['team_id']), None)
        if team_index is not None:
            queue[team_index]['status'] = 'RUNNING'
            flash(f'Team {run_data["team_id"]} run in Slot {slot_id} has been RESUMED.', 'success')
    else:
        flash(f'Slot {slot_id} is not paused or dysfunctional.', 'error')
    return redirect(url_for('index'))


@app.route('/mark_dysfunctional', methods=['POST'])
def mark_dysfunctional():
    slot_id = int(request.form['slot_id'])
    run_data = active_runs.get(slot_id)

    if run_data and run_data['status'] == 'RUNNING':
        # Calculate and store remaining time
        time_rem = get_time_remaining(run_data)
        team_id = run_data['team_id']
        
        # 1. Update the active run slot status
        run_data.update({
            'status': 'DYSFUNCTIONAL',
            'time_paused_at': time.time(),
            'time_remaining': time_rem
        })
        
        # 2. Update the queue item: status to PAUSED, and set priority_re_run flag
        team_index = next((i for i, item in enumerate(queue) if item['team_id'] == team_id and item['status'] == 'RUNNING'), None)
        if team_index is not None:
            queue[team_index]['status'] = 'PAUSED' # Keep it PAUSED until review/resume
            queue[team_index]['priority_re_run'] = True # Set the priority flag
            flash(f'Team {team_id} run in Slot {slot_id} marked as DYSFUNCTIONAL. It can be resumed or sent to review.', 'warning')
    else:
        flash(f'Slot {slot_id} is NOT running.', 'error')
        
    return redirect(url_for('index'))

@app.route('/end_run', methods=['POST'])
def end_run():
    slot_id = int(request.form['slot_id'])
    run_data = active_runs.get(slot_id)
    
    if run_data and run_data['team_id']:
        team_id = run_data['team_id']
        
        # 1. Update the team's status in the queue to REVIEW
        team_index = next((i for i, item in enumerate(queue) if item['team_id'] == team_id and item['status'] in ('RUNNING', 'PAUSED')), None)
        if team_index is not None:
            queue[team_index]['status'] = 'REVIEW'
            # If it was dysfunctional, the priority_re_run flag remains true for the review stage
            flash(f'Team {team_id} run in Slot {slot_id} ended and moved to REVIEW Queue.', 'success')
            
        # 2. Clear the active slot
        active_runs[slot_id] = {'team_id': None, 'start_time': None, 'status': 'IDLE', 'time_paused_at': None, 'time_remaining': None}
    else:
        flash(f'Slot {slot_id} has no active run to end.', 'error')
        
    return redirect(url_for('index'))

# --- Review Queue Actions ---

def handle_review_action(team_id, action_status, clear_flag):
    """Handles logic for marking runs as SUCCESS, FAILURE, or CANCELED."""
    team_index = next((i for i, item in enumerate(queue) if item['team_id'] == team_id and item['status'] == 'REVIEW'), None)
    
    if team_index is None:
        flash(f'Team {team_id} not found in the review queue.', 'error')
        return redirect(url_for('index'))
        
    if action_status == 'SUCCESS':
        # Increment run count
        teams_history[team_id] = teams_history.get(team_id, 0) + 1
        # Remove from queue
        queue.pop(team_index)
        flash(f'Team {team_id} run marked as SUCCESSFUL. Run count incremented.', 'success')
        
    elif action_status == 'FAILURE':
        # Technical Failure means we don't count the run and re-add them to the queue with priority
        queue[team_index]['status'] = 'WAITING'
        queue[team_index]['priority_re_run'] = True # Ensure they get highest WAITING priority
        flash(f'Team {team_id} run marked as TECHNICAL FAILURE. Re-added to waiting queue with PRIORITY.', 'warning')
        
    elif action_status == 'CANCELED':
        # Remove from queue (no count increment)
        queue.pop(team_index)
        flash(f'Team {team_id} run marked as CANCELED. Run count not affected.', 'error')
        
    return redirect(url_for('index'))

@app.route('/mark_success', methods=['POST'])
def mark_success():
    team_id = request.form['team_id']
    return handle_review_action(team_id, 'SUCCESS', True)

@app.route('/mark_failure', methods=['POST'])
def mark_failure():
    team_id = request.form['team_id']
    # FAILURE means re-add to WAITING with priority_re_run = True
    return handle_review_action(team_id, 'FAILURE', False)

@app.route('/mark_canceled', methods=['POST'])
def mark_canceled():
    team_id = request.form['team_id']
    return handle_review_action(team_id, 'CANCELED', True)

# --- Settings ---

@app.route('/set_run_time', methods=['POST'])
def set_run_time():
    global RUN_TIME_SECONDS
    try:
        minutes = int(request.form['run_time_minutes'])
        if minutes <= 0:
            raise ValueError
        RUN_TIME_SECONDS = minutes * 60
        flash(f'Run time updated to {minutes} minutes.', 'success')
    except ValueError:
        flash('Invalid run time. Must be a positive integer.', 'error')
    return redirect(url_for('index'))

if __name__ == '__main__':
    # Initial seed data for testing the new sorting
    # TEST CASE SCENARIO:
    # TEAM_D (0 runs) should be #1.
    # TEAM_B (1 run, PRIORITY) should be #2.
    # TEAM_E (0 runs, but joins after D) is also 0 runs, so will be behind D by FIFO, but still Tier 1.
    # TEAM_C (2 runs, No Priority) should be #4.
    # TEAM_A (3 runs, No Priority) should be #5.
    
    # For testing see below

    # if not teams_history:
    #     teams_history = {'TEAM_A': 3, 'TEAM_B': 1, 'TEAM_C': 2, 'TEAM_D': 0}
        
    # if not queue:
    #     queue.append({'team_id': 'TEAM_A', 'status': 'WAITING', 'priority_re_run': False, 'time_added': time.time() - 4}) # 3 runs, Joins earliest
    #     queue.append({'team_id': 'TEAM_C', 'status': 'WAITING', 'priority_re_run': False, 'time_added': time.time() - 3}) # 2 runs
    #     queue.append({'team_id': 'TEAM_B', 'status': 'WAITING', 'priority_re_run': True, 'time_added': time.time() - 2}) # 1 run, PRIORITY
    #     queue.append({'team_id': 'TEAM_D', 'status': 'WAITING', 'priority_re_run': False, 'time_added': time.time() - 1}) # 0 runs, Joins later
    #     queue.append({'team_id': 'TEAM_E', 'status': 'WAITING', 'priority_re_run': False, 'time_added': time.time()}) # 0 runs, Joins last
        
        # Expected order: D, E, B, C, A

    app.run(debug=True)