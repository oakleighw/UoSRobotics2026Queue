// Confirmation function for actions
function confirmAction(action, message) {
    return confirm(message);
}

const AUTH_CONFIG = {
    username: 'oakleighsrosq',
    password: 'DiamondROSArena26P4ss',
    sessionKey: 'queue_controls_unlocked'
};

function initializeInteractionGate() {
    const overlay = document.getElementById('auth-overlay');
    const appRoot = document.getElementById('app-root');
    const authForm = document.getElementById('auth-form');
    const authUser = document.getElementById('auth-username');
    const authPass = document.getElementById('auth-password');
    const authError = document.getElementById('auth-error');
    const authCloseBtn = document.getElementById('auth-close-btn');
    const authOpenBtn = document.getElementById('auth-open-btn');

    if (!overlay || !appRoot || !authForm || !authUser || !authPass || !authError || !authCloseBtn || !authOpenBtn) {
        return;
    }

    const showOverlay = () => {
        overlay.classList.remove('hidden');
        authOpenBtn.classList.add('hidden');
        authUser.focus();
    };

    const hideOverlay = () => {
        overlay.classList.add('hidden');
        authOpenBtn.classList.remove('hidden');
    };

    const lockApp = () => {
        appRoot.classList.add('app-locked');
        appRoot.setAttribute('inert', '');
        appRoot.setAttribute('aria-hidden', 'true');
        showOverlay();
    };

    const unlockApp = () => {
        appRoot.classList.remove('app-locked');
        appRoot.removeAttribute('inert');
        appRoot.setAttribute('aria-hidden', 'false');
        overlay.classList.add('hidden');
        authOpenBtn.classList.add('hidden');
    };

    if (sessionStorage.getItem(AUTH_CONFIG.sessionKey) === 'true') {
        unlockApp();
        return;
    }

    lockApp();

    authCloseBtn.addEventListener('click', () => {
        authError.textContent = '';
        hideOverlay();
    });

    document.addEventListener('keydown', (event) => {
        if (event.key === 'Escape' && !overlay.classList.contains('hidden') && appRoot.classList.contains('app-locked')) {
            authError.textContent = '';
            hideOverlay();
        }
    });

    authOpenBtn.addEventListener('click', () => {
        showOverlay();
    });

    authForm.addEventListener('submit', (event) => {
        event.preventDefault();

        const enteredUser = authUser.value.trim();
        const enteredPass = authPass.value;

        if (enteredUser === AUTH_CONFIG.username && enteredPass === AUTH_CONFIG.password) {
            sessionStorage.setItem(AUTH_CONFIG.sessionKey, 'true');
            authError.textContent = '';
            unlockApp();
            return;
        }

        authError.textContent = 'Incorrect username or password.';
        authPass.value = '';
        authPass.focus();
    });
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

initializeInteractionGate();

// Update timers every second
setInterval(updateTimers, 1000);
