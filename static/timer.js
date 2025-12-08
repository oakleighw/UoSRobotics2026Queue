/**
 * Handles the client-side countdown display for the active run.
 * This script requires 'data-seconds-remaining' and 'data-status' 
 * attributes on the timer element.
 */
function initializeCountdown() {
    const timerElement = document.getElementById('active-run-timer-display');

    if (!timerElement) {
        console.error("Timer element not found. Check for ID 'active-run-timer-display'.");
        return;
    }

    // Retrieve initial data passed from the Flask template
    let totalSeconds = parseInt(timerElement.getAttribute('data-seconds-remaining') || '0', 10);
    const status = timerElement.getAttribute('data-status');

    let countdownInterval;

    function updateTimerDisplay() {
        if (totalSeconds <= 0) {
            timerElement.textContent = "00:00";
            if (countdownInterval) {
                clearInterval(countdownInterval);
            }
            // Optionally, refresh the page when timer expires to trigger server-side queue logic display
            // setTimeout(() => window.location.reload(), 2000); 
            return;
        }

        const minutes = Math.floor(totalSeconds / 60);
        const seconds = totalSeconds % 60;
        
        // Format to MM:SS
        const timeString = `${minutes.toString().padStart(2, '0')}:${seconds.toString().padStart(2, '0')}`;
        timerElement.textContent = timeString;

        // Decrement every second
        totalSeconds--; 
    }

    // Only start the countdown if the run is active and running
    if (totalSeconds > 0 && status === "RUNNING") {
        updateTimerDisplay(); // Initial display
        countdownInterval = setInterval(updateTimerDisplay, 1000); 
    } else {
        // For PAUSED/DYSFUNCTIONAL, ensure the initial static time is set if possible
        updateTimerDisplay();
    }
}

// Run the initialization function once the entire page is loaded
document.addEventListener('DOMContentLoaded', initializeCountdown);