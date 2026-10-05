/**
 * signup_voice.js — Voice enrollment page logic
 *
 * Manages:
 *  - Paragraph line highlighting as user reads
 *  - Start/Stop recording with VoiceRecorder
 *  - Waveform visualiser (animated bars)
 *  - Audio preview before submitting
 *  - POST to /auth/signup/voice/submit
 *  - Redirect to /auth/signup/details?token=...
 */

(() => {
  // ── DOM References ─────────────────────────────────────────
  const recordBtn      = document.getElementById('record-btn');
  const recordLabel    = document.getElementById('record-label');
  const recordStatus   = document.getElementById('record-status');
  const waveformBars   = document.querySelectorAll('.waveform-bar');
  const audioPreviewer = document.getElementById('audio-preview');
  const audioEl        = document.getElementById('audio-player');
  const submitBtn      = document.getElementById('submit-btn');
  const submitStatus   = document.getElementById('submit-status');
  const lineItems      = document.querySelectorAll('.paragraph-line');

  const progressWrap   = document.getElementById('rec-progress-wrap');
  const progressBar    = document.getElementById('rec-progress');
  const timerEl        = document.getElementById('rec-timer');

  let recorder  = null;
  let audioBlob = null;
  let currentLine = 0;
  let recStartMs  = 0;
  let tickHandle  = null;
  let levelSum    = 0;
  let levelCount  = 0;

  const TARGET_S    = 25;   // comfortable full read of 6 sentences
  const MIN_S       = 8;    // below this the server rejects anyway
  const AUTO_STOP_S = 45;   // nobody needs longer; saves user time
  const SECS_PER_LINE = TARGET_S / lineItems.length;

  // ── Waveform update ────────────────────────────────────────
  function updateWaveform(level, freqData) {
    const n = waveformBars.length;
    for (let i = 0; i < n; i++) {
      const binIndex = Math.floor((i / n) * (freqData.length / 2));
      const raw = level === 0 ? 4 : Math.max(4, (freqData[binIndex] / 255) * 56);
      waveformBars[i].style.height = raw + 'px';
    }
    if (recorder && recorder.isRecording) { levelSum += level; levelCount++; }
  }

  // ── Timer / progress / auto line-advance ──────────────────
  function tick() {
    const elapsed = (Date.now() - recStartMs) / 1000;
    const m = Math.floor(elapsed / 60);
    const s = Math.floor(elapsed % 60).toString().padStart(2, '0');
    timerEl.textContent = `${m}:${s}`;
    progressBar.style.width = Math.min(100, (elapsed / TARGET_S) * 100) + '%';

    // Advance the highlighted sentence at a natural reading pace
    const lineIdx = Math.min(lineItems.length - 1, Math.floor(elapsed / SECS_PER_LINE));
    if (lineIdx !== currentLine) setActiveLine(lineIdx);

    // Gentle low-volume hint after 4s of speaking
    if (elapsed > 4 && levelCount > 0 && (levelSum / levelCount) < 0.02) {
      recordStatus.textContent = '🔉 Your voice is very quiet — move closer to the mic';
      recordStatus.className = 'record-status recording';
    }

    if (elapsed >= AUTO_STOP_S && recorder && recorder.isRecording) {
      stopRecording();
    }
  }

  function stopRecording() {
    if (!recorder || !recorder.isRecording) return;
    recorder.stop();
    clearInterval(tickHandle);
    recordBtn.classList.remove('recording');
    recordBtn.textContent = '🎙️';
    recordLabel.textContent = 'Start Recording';
    recordStatus.textContent = 'Processing...';
    recordStatus.className = 'record-status';
  }

  // ── Highlight paragraph line ───────────────────────────────
  function setActiveLine(idx) {
    lineItems.forEach((el, i) => {
      el.classList.remove('active');
      if (i < idx) el.classList.add('done');
    });
    if (lineItems[idx]) {
      lineItems[idx].classList.add('active');
      lineItems[idx].scrollIntoView({ behavior: 'smooth', block: 'center' });
    }
    currentLine = idx;
  }

  // ── Recording toggle ───────────────────────────────────────
  recordBtn.addEventListener('click', async () => {
    if (recorder && recorder.isRecording) {
      stopRecording();
      return;
    }

    // Start recording
    audioBlob = null;
    submitBtn.disabled = true;
    audioPreviewer.style.display = 'none';
    recordStatus.textContent = 'Requesting microphone...';

    recorder = new VoiceRecorder({
      onStart: () => {
        recordBtn.classList.add('recording');
        recordBtn.textContent = '⏹';
        recordLabel.textContent = 'Stop Recording';
        recordStatus.textContent = '● Recording... follow the highlighted sentence';
        recordStatus.className = 'record-status recording';
        recStartMs = Date.now();
        levelSum = 0; levelCount = 0;
        progressWrap.style.display = 'block';
        tickHandle = setInterval(tick, 250);
        setActiveLine(0);
      },
      onStop: (blob) => {
        audioBlob = blob;
        clearInterval(tickHandle);
        const elapsed = (Date.now() - recStartMs) / 1000;
        const url = URL.createObjectURL(blob);
        audioEl.src = url;
        audioPreviewer.style.display = 'block';
        updateWaveform(0, new Uint8Array(64));
        lineItems.forEach(el => { el.classList.add('done'); el.classList.remove('active'); });

        if (elapsed < MIN_S) {
          // Too short — the server would reject it; save the round-trip
          submitBtn.disabled = true;
          recordStatus.textContent = `⚠️ Only ${elapsed.toFixed(0)}s recorded — please record again and read all 6 sentences (at least ${MIN_S}s)`;
          recordStatus.className = 'record-status';
        } else {
          submitBtn.disabled = false;
          recordStatus.textContent = '✅ Recording complete — preview and submit';
          recordStatus.className = 'record-status done';
        }
      },
      onVolumeChange: updateWaveform,
      onError: (err) => {
        recordStatus.textContent = '❌ Microphone error: ' + err.message;
        recordStatus.className = 'record-status';
        console.error(err);
      },
    });

    await recorder.start();
  });

  // ── Submit enrollment ──────────────────────────────────────
  submitBtn.addEventListener('click', async () => {
    if (!audioBlob) return;

    submitBtn.disabled = true;
    submitBtn.innerHTML = '<span class="spinner"></span> Processing...';
    submitStatus.textContent = '';
    submitStatus.className = 'alert';

    const formData = new FormData();
    formData.append('audio', audioBlob, 'enrollment.webm');

    try {
      const res = await fetch('/auth/signup/voice/submit', {
        method: 'POST',
        body: formData,
      });
      const data = await res.json();

      if (data.success) {
        const qualityLabel = { excellent: '⭐ Excellent', good: '👍 Good', okay: '✔️ Okay' }[data.quality] || '';
        submitStatus.textContent = `✅ Voice signature created! Quality: ${qualityLabel} (${data.duration_s}s of clear speech)`;
        submitStatus.className = 'alert alert-success';
        submitBtn.innerHTML = '✅ Redirecting...';
        setTimeout(() => {
          window.location.href = `/auth/signup/details?token=${encodeURIComponent(data.token)}`;
        }, 1200);
      } else {
        submitStatus.textContent = '❌ ' + (data.detail || data.error || 'Something went wrong.');
        submitStatus.className = 'alert alert-error';
        submitBtn.disabled = false;
        submitBtn.innerHTML = 'Submit Voice Signature';
      }
    } catch (err) {
      submitStatus.textContent = '❌ Network error: ' + err.message;
      submitStatus.className = 'alert alert-error';
      submitBtn.disabled = false;
      submitBtn.innerHTML = 'Submit Voice Signature';
    }
  });

  // ── Init: idle waveform animation ─────────────────────────
  function idleWaveform() {
    waveformBars.forEach((bar, i) => {
      const h = 4 + Math.random() * 6;
      bar.style.height = h + 'px';
    });
    setTimeout(idleWaveform, 600);
  }
  idleWaveform();
  setActiveLine(0);
})();
