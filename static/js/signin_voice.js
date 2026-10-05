/**
 * signin_voice.js — Two-step signin logic
 *
 * Step 1: POST username + password → receive temp_token
 * Step 2: Voice challenge → say "PARTH" → POST audio → receive session cookie
 */

(() => {
  // ── Step 1 DOM ─────────────────────────────────────────────
  const step1Panel    = document.getElementById('step1-panel');
  const loginForm     = document.getElementById('login-form');
  const loginBtn      = document.getElementById('login-btn');
  const loginError    = document.getElementById('login-error');

  // ── Step 2 DOM ─────────────────────────────────────────────
  const step2Panel      = document.getElementById('step2-panel');
  const tempTokenInput  = document.getElementById('temp-token');
  const challengeRecBtn = document.getElementById('challenge-record-btn');
  const challengeLabel  = document.getElementById('challenge-label');
  const challengeStatus = document.getElementById('challenge-status');
  const waveformBars    = document.querySelectorAll('.challenge-waveform-bar');
  const voiceError      = document.getElementById('voice-error');
  const retryBtn        = document.getElementById('retry-btn');

  let recorder   = null;
  let audioBlob  = null;
  let tempToken  = null;
  let autoStopTimer = null;

  // ── Waveform helper ────────────────────────────────────────
  function updateWaveform(level, freqData) {
    const n = waveformBars.length;
    for (let i = 0; i < n; i++) {
      const bin = Math.floor((i / n) * Math.min(freqData.length / 2, 32));
      const h = level === 0 ? 4 : Math.max(4, (freqData[bin] / 255) * 52);
      waveformBars[i].style.height = h + 'px';
    }
  }

  // ── Step 1: Login ──────────────────────────────────────────
  loginForm.addEventListener('submit', async (e) => {
    e.preventDefault();
    loginError.textContent = '';
    loginError.className   = 'alert';

    const username = document.getElementById('username').value.trim();
    const password = document.getElementById('password').value;

    if (!username || !password) {
      loginError.textContent = 'Please enter username and password.';
      loginError.className   = 'alert alert-error';
      return;
    }

    loginBtn.disabled = true;
    loginBtn.innerHTML = '<span class="spinner"></span> Verifying...';

    try {
      const res  = await fetch('/auth/signin/submit', {
        method:  'POST',
        headers: { 'Content-Type': 'application/json' },
        body:    JSON.stringify({ username, password }),
      });
      const data = await res.json();

      if (data.success) {
        tempToken = data.temp_token;
        // Show this signin's unique challenge words
        const passEl = document.getElementById('passphrase-word');
        if (passEl && data.challenge) passEl.textContent = data.challenge.toUpperCase();
        // Transition to Step 2
        step1Panel.classList.add('hidden');
        step2Panel.classList.remove('hidden');
        step2Panel.classList.add('slide-enter');
      } else {
        loginError.textContent = data.error || 'Login failed.';
        loginError.className   = 'alert alert-error';
        if (data.remaining_attempts !== undefined) {
          loginError.textContent += ` (${data.remaining_attempts} attempts left)`;
        }
        loginBtn.disabled = false;
        loginBtn.innerHTML = 'Continue';
      }
    } catch (err) {
      loginError.textContent = '❌ Network error: ' + err.message;
      loginError.className   = 'alert alert-error';
      loginBtn.disabled = false;
      loginBtn.innerHTML = 'Continue';
    }
  });

  // ── Step 2: Voice Challenge ────────────────────────────────
  async function startVoiceChallenge() {
    voiceError.textContent  = '';
    voiceError.className    = 'alert';
    challengeStatus.textContent = '● Recording — say the words shown above';
    challengeStatus.className = 'record-status recording';
    challengeRecBtn.classList.add('recording');
    challengeRecBtn.textContent = '⏹';
    challengeLabel.textContent = 'Stop';

    recorder = new VoiceRecorder({
      onStart: () => {
        // Recording started — user can manually stop
      },
      onStop: async (blob) => {
        audioBlob = blob;
        challengeRecBtn.classList.remove('recording');
        challengeRecBtn.textContent = '🎙️';
        challengeLabel.textContent = 'Record';
        challengeStatus.textContent = 'Processing...';
        challengeStatus.className = 'record-status';
        updateWaveform(0, new Uint8Array(32));
        await submitVoice(blob);
      },
      onVolumeChange: updateWaveform,
      onError: (err) => {
        challengeStatus.textContent = '❌ Mic error: ' + err.message;
        challengeStatus.className   = 'record-status';
      },
    });

    await recorder.start();
  }

  function stopVoiceChallenge() {
    if (recorder && recorder.isRecording) recorder.stop();
    if (autoStopTimer) clearTimeout(autoStopTimer);
  }

  challengeRecBtn.addEventListener('click', () => {
    if (recorder && recorder.isRecording) {
      stopVoiceChallenge();
    } else {
      startVoiceChallenge();
    }
  });

  // ── Submit voice ───────────────────────────────────────────
  async function submitVoice(blob) {
    voiceError.textContent = '';
    challengeStatus.textContent = 'Verifying voice...';

    const formData = new FormData();
    formData.append('audio', blob, 'challenge.webm');
    formData.append('temp_token', tempToken);

    try {
      const res  = await fetch('/auth/signin/voice', { method: 'POST', body: formData });
      const data = await res.json();

      if (data.success) {
        challengeStatus.textContent = `✅ Authenticated! (score: ${data.score?.toFixed(2)})`;
        challengeStatus.className   = 'record-status done';
        setTimeout(() => { window.location.href = data.redirect || '/dashboard'; }, 800);
      } else {
        voiceError.textContent = data.error || 'Voice not recognised.';
        if (data.score !== undefined) {
          voiceError.textContent += ` (score: ${data.score?.toFixed(3)}, threshold: ${data.threshold})`;
        }
        voiceError.className = 'alert alert-error';
        challengeStatus.textContent = 'Try again';
        challengeStatus.className   = 'record-status';
        if (retryBtn) retryBtn.style.display = 'block';
      }
    } catch (err) {
      voiceError.textContent = '❌ Network error: ' + err.message;
      voiceError.className   = 'alert alert-error';
    }
  }

  if (retryBtn) {
    retryBtn.addEventListener('click', () => {
      retryBtn.style.display = 'none';
      startVoiceChallenge();
    });
  }

  // ── Idle waveform ──────────────────────────────────────────
  function idleWave() {
    waveformBars.forEach(bar => {
      bar.style.height = (4 + Math.random() * 5) + 'px';
    });
    setTimeout(idleWave, 700);
  }
  idleWave();
})();
