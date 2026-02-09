// Confirmation function for actions
function confirmAction(action, message) {
    return confirm(message);
}

// Timer Logic
function formatTime(seconds) {
    const minutes = Math.floor(seconds / 60);
    const remainingSeconds = Math.floor(seconds % 60);
    return `${minutes.toString().padStart(2, '0')}:${remainingSeconds.toString().padStart(2, '0')}`;
}

function updateTimers() {
    // Update Session Timer
    const sessionElem = document.getElementById('session-timer');
    if (sessionElem) {
        let rem = parseInt(sessionElem.getAttribute('data-remaining'));
        if (rem > 0) {
            rem -= 1;
            sessionElem.setAttribute('data-remaining', rem);
            sessionElem.innerText = formatTime(rem);

            // Visual warning when low
            if (rem < 300) sessionElem.classList.add('text-red-500');
        } else {
            sessionElem.innerText = "00:00";
        }
    }

    // Update Arena Slot Timers
    document.querySelectorAll('[data-seconds-remaining]').forEach(timerElement => {
        let seconds = parseInt(timerElement.getAttribute('data-seconds-remaining'));
        const status = timerElement.getAttribute('data-status');

        if (status === 'RUNNING' && seconds > 0) {
            seconds--;
            timerElement.setAttribute('data-seconds-remaining', seconds);
            timerElement.innerHTML = `${formatTime(seconds)}`;
        } else if (seconds <= 0) {
            timerElement.innerHTML = `00:00`;
            if (status === 'RUNNING') {
                // Reload the page when a run times out to refresh the queue/review status
                window.location.reload();
            }
        }
    });
}

function filterTally() {
    const input = document.getElementById('tally-search');
    const filter = input.value.toUpperCase();

    // 1. Filter Team Runs Tally
    const tallyList = document.querySelector('.tally-list');
    if (tallyList) {
        const tallyItems = tallyList.querySelectorAll('.flex.justify-between.items-center');
        tallyItems.forEach(item => {
            const teamIdElement = item.querySelector('span.font-semibold.text-gray-800');
            if (teamIdElement) {
                const teamId = teamIdElement.textContent || teamIdElement.innerText;
                if (teamId.toUpperCase().indexOf(filter) > -1) {
                    item.style.display = "flex";
                } else {
                    item.style.display = "none";
                }
            }
        });
    }
}

// Update timers every second
setInterval(updateTimers, 1000);
