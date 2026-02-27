// Confirmation function for actions
function confirmAction(action, message) {
    return confirm(message);
}

const AUTH_CONFIG = {
    loginEndpoint: '/auth/login',
    logoutEndpoint: '/auth/logout'
};

let serverClockOffsetSeconds = 0;

function initializeInteractionGate() {
    const overlay = document.getElementById('auth-overlay');
    const appRoot = document.getElementById('app-root');
    const authForm = document.getElementById('auth-form');
    const authUser = document.getElementById('auth-username');
    const authPass = document.getElementById('auth-password');
    const authError = document.getElementById('auth-error');
    const authCloseBtn = document.getElementById('auth-close-btn');
    const authOpenBtn = document.getElementById('auth-open-btn');
    let isUnlocked = appRoot.getAttribute('data-auth-unlocked') === 'true';

    if (!overlay || !appRoot || !authForm || !authUser || !authPass || !authError || !authCloseBtn || !authOpenBtn) {
        return;
    }

    const showOverlay = () => {
        overlay.classList.remove('hidden');
        authUser.focus();
    };

    const hideOverlay = () => {
        overlay.classList.add('hidden');
    };

    const setAuthButtonState = () => {
        authOpenBtn.textContent = isUnlocked ? 'Logout' : 'Login';
        authOpenBtn.setAttribute('aria-label', isUnlocked ? 'Log out' : 'Open login');
    };

    const lockApp = () => {
        isUnlocked = false;
        appRoot.setAttribute('data-auth-unlocked', 'false');
        appRoot.classList.add('app-locked');
        appRoot.setAttribute('inert', '');
        appRoot.setAttribute('aria-hidden', 'true');
        hideOverlay();
        setAuthButtonState();
    };

    const unlockApp = () => {
        isUnlocked = true;
        appRoot.setAttribute('data-auth-unlocked', 'true');
        appRoot.classList.remove('app-locked');
        appRoot.removeAttribute('inert');
        appRoot.setAttribute('aria-hidden', 'false');
        hideOverlay();
        setAuthButtonState();
    };

    if (isUnlocked) {
        unlockApp();
    } else {
        lockApp();
    }

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

    authOpenBtn.addEventListener('click', async () => {
        if (isUnlocked) {
            try {
                const response = await fetch(AUTH_CONFIG.logoutEndpoint, { method: 'POST' });
                if (!response.ok) {
                    return;
                }
            } catch (error) {
                return;
            }

            authError.textContent = '';
            authForm.reset();
            lockApp();
            return;
        }

        showOverlay();
    });

    authForm.addEventListener('submit', async (event) => {
        event.preventDefault();

        const enteredUser = authUser.value.trim();
        const enteredPass = authPass.value;

        try {
            const response = await fetch(AUTH_CONFIG.loginEndpoint, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({
                    username: enteredUser,
                    password: enteredPass
                })
            });

            const result = await response.json().catch(() => ({}));

            if (response.ok && result.ok) {
                authError.textContent = '';
                authForm.reset();
                unlockApp();
                return;
            }

            authError.textContent = result.error || 'Incorrect username or password.';
            authPass.value = '';
            authPass.focus();
        } catch (error) {
            authError.textContent = 'Login failed. Please try again.';
        }
    });
}

// Timer Logic
function formatTime(seconds) {
    const minutes = Math.floor(seconds / 60);
    const remainingSeconds = Math.floor(seconds % 60);
    return `${minutes.toString().padStart(2, '0')}:${remainingSeconds.toString().padStart(2, '0')}`;
}

function getServerNowSeconds() {
    return (Date.now() / 1000) + serverClockOffsetSeconds;
}

function updateTimers() {
    // Update Session Timer
    const sessionElem = document.getElementById('session-timer');
    if (sessionElem) {
        const sessionEndTs = parseFloat(sessionElem.getAttribute('data-session-end-ts') || '0');
        if (sessionEndTs > 0) {
            const rem = Math.max(0, Math.floor(sessionEndTs - getServerNowSeconds()));
            sessionElem.innerText = formatTime(rem);

            if (rem < 300) {
                sessionElem.classList.add('text-red-500');
            } else {
                sessionElem.classList.remove('text-red-500');
            }
        } else {
            sessionElem.innerText = 'OFFLINE';
            sessionElem.classList.remove('text-red-500');
        }
    }

    // Update Arena Slot Timers
    document.querySelectorAll('[data-seconds-remaining]').forEach(timerElement => {
        let seconds = parseInt(timerElement.getAttribute('data-seconds-remaining') || '0');
        const status = timerElement.getAttribute('data-status');

        if (status === 'RUNNING') {
            const endTs = parseFloat(timerElement.getAttribute('data-end-ts') || '0');
            if (endTs > 0) {
                seconds = Math.max(0, Math.floor(endTs - getServerNowSeconds()));
                timerElement.setAttribute('data-seconds-remaining', seconds);
            }

            timerElement.innerHTML = `${formatTime(seconds)}`;

            if (seconds <= 0) {
                window.location.reload();
            }
        } else if (seconds <= 0) {
            timerElement.innerHTML = `00:00`;
        }
    });
}

function initializeStatePolling() {
    const appRoot = document.getElementById('app-root');
    if (!appRoot) {
        return;
    }

    const initialServerNow = parseFloat(appRoot.getAttribute('data-server-now') || '0');
    if (initialServerNow > 0) {
        serverClockOffsetSeconds = initialServerNow - (Date.now() / 1000);
    }

    let lastStateSignature = appRoot.getAttribute('data-state-signature') || '';

    setInterval(async () => {
        try {
            const response = await fetch('/state_version', { cache: 'no-store' });
            if (!response.ok) {
                return;
            }

            const data = await response.json();
            if (typeof data.server_now === 'number') {
                serverClockOffsetSeconds = data.server_now - (Date.now() / 1000);
            }

            if (data.state_signature && data.state_signature !== lastStateSignature) {
                window.location.reload();
            }
        } catch (error) {
        }
    }, 2000);
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
initializeStatePolling();

// Update timers every second
setInterval(updateTimers, 1000);
updateTimers();
