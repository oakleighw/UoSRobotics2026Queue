# Waffle Robotics Arena Run Queue

Manage team runs and status for 4 concurrent arena slots.


# Prerequisites

Python

# Installing on WSL Laptops

To save time, you can clone this repo into the WSL-ROS2 environment (git & python already installed):

```Bash
git clone https://github.com/oakleighw/UoSRobotics2026Queue.git
```
Then run the following to install flask (into a new environment) within the WSL instance:

```Bash
python3 -m venv venv
source venv/bin/activate
pip install flask
```
## Installation (everywhere else)
Ensuring python is installed:

```Bash
pip install flask
```

## Run
In directory context:
```Bash
python app.py
```

## Security Environment Variables for PythonAnywhere (recommended)

Set these in your host environment (for PythonAnywhere, add them in your web app config / WSGI setup):

```Bash
FLASK_SECRET_KEY= ""
QUEUE_AUTH_USERNAME=""
QUEUE_AUTH_PASSWORD=""
```

- `FLASK_SECRET_KEY` protects Flask sessions/cookies.
- `QUEUE_AUTH_USERNAME` and `QUEUE_AUTH_PASSWORD` control the staff login.

## 💡 Instructions

### 1. Joining the Queue

* Go to the **"➕ Join Queue"** card (Purple).

* Enter the team's ID (e.g., \`1\`, \`B\`, or \`1B\`).

* Click **"Add Team to Waitlist"**. The team will appear in the **Waiting Queue**.

### 2. Starting a Run

* Locate an **IDLE** slot in the **"🤖 Arena Status"** section.

* If the **Waiting Queue** is not empty, a **"▶️ Start \[Team ID\]"** button will appear on the IDLE slot.

* Click **"Start"** to move the team at the front of the queue into that slot, beginning the timer.

### 3. Managing Active Runs

* **Pause/Resume:** Use the **⏸️** button to pause the timer, and the **▶️** button to resume.

* **Mark Dysfunctional (⚠️):** Use this if a robot breaks or there's an immediate technical problem, sending the team to **Review** for a likely Priority Re-run.

* **End Run (❌):** Use this when the run is complete or manually terminated. This sends the team to the **Review Queue**.

### 4. Processing the Review Queue

After a run ends or is marked dysfunctional and cancelled, it moves to the **Review Queue**.

* **SUCCESS:** Team completed the run successfully. Removes team from review and increments their count in the **Tally**.

* **FAILURE:** Marks a run as a technical failure (e.g., code won't run at all). Removes team from review, **doesn't** increment their Tally count, and sets a **Priority Re-run** flag in the next queue entry.

* **CANCELED:** Run was cancelled by the team/operator (e.g., they didn't show up). Removes the team entirely from the queue/review without incrementing the **Tally**.

### 5. Team Runs Tally

* Shows the total number of **Successful** runs completed by each team.

* Use the search bar to filter for specific teams.

* **Re-add (🔄):** Adds a team back to the **Waiting Queue** for another run (don't have to enter manually).

* **Delete (🗑️):** Permanently deletes the team and all run history (use with caution).

### 6. Settings

* **Set Run Time:** Change the standard length of time (in minutes) for a robot run.

* **Team Name Prefix:** Change the display prefix for all teams (e.g., change from "Team _" to "Group _").
