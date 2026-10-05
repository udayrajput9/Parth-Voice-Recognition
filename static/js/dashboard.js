/**
 * dashboard.js — Dashboard voice verification logic
 *
 * Manages:
 *  - Per-line mic button → record → submit → terminal output
 *  - Waveform visualiser on canvas in terminal header
 *  - Stats counters (total, authenticated, failed)
 *  - Terminal output with timestamps
 *  - Auto-stop after 8 seconds
 */

(() => {
  // ── DOM References ─────────────────────────────────────────
  const terminalBody   = document.getElementById('terminal-body');
  const terminalCanvas = document.getElementById('terminal-canvas');
  const clearBtn       = document.getElementById('clear-terminal');
  const statTotal      = document.getElementById('stat-total');
  const statAuth       = document.getElementById('stat-auth');
  const statFailed     = document.getElementById('stat-failed');

  // ── State ──────────────────────────────────────────────────
  let stats       = { total: 0, auth: 0, failed: 0 };
  let recorder    = null;
  let activeLineEl = null;
  let autoStopTimer = null;
  const LINE_MAX_SECONDS = 8;

  // ── Canvas waveform ────────────────────────────────────────
  const ctx = terminalCanvas ? terminalCanvas.getContext('2d') : null;

  function drawCanvas(level, freqData) {
    if (!ctx || !terminalCanvas) return;
    const W = terminalCanvas.width;
    const H = terminalCanvas.height;
    ctx.clearRect(0, 0, W, H);

    const barCount = 48;
    const barW = W / (barCount * 2);
    const gap   = barW;

    for (let i = 0; i < barCount; i++) {
      const bin = Math.floor((i / barCount) * (freqData.length / 2));
      const h = level === 0
        ? 2
        : Math.max(2, (freqData[bin] / 255) * (H - 4));

      const x = i * (barW + gap) + gap / 2;
      const grad = ctx.createLinearGradient(x, H, x, H - h);
      grad.addColorStop(0, 'rgba(124,58,237,0.9)');
      grad.addColorStop(1, 'rgba(6,182,212,0.9)');

      ctx.fillStyle = grad;
      ctx.beginPath();
      ctx.roundRect(x, H - h, barW, h, 2);
      ctx.fill();
    }
  }

  // ── Terminal output ────────────────────────────────────────
  function writeToTerminal(text, type = 'info') {
    const now   = new Date();
    const ts    = now.toTimeString().slice(0, 8);
    const line  = document.createElement('div');
    line.className = 'terminal-line';
    line.innerHTML = `
      <span class="terminal-prompt">[${ts}]$</span>
      <span class="terminal-out ${type}">${escapeHtml(text)}</span>
    `;
    terminalBody.appendChild(line);
    terminalBody.scrollTop = terminalBody.scrollHeight;
  }

  function escapeHtml(str) {
    return str
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;');
  }

  // ── Update stats ───────────────────────────────────────────
  function updateStats(result) {
    stats.total++;
    if (result.authenticated) stats.auth++;
    else stats.failed++;
    if (statTotal)  statTotal.textContent  = stats.total;
    if (statAuth)   statAuth.textContent   = stats.auth;
    if (statFailed) statFailed.textContent = stats.failed;
  }

  // ── Mark line with result ──────────────────────────────────
  function markLine(lineEl, result) {
    lineEl.classList.remove('recording', 'active');
    const statusEl = lineEl.querySelector('.line-status');
    const micBtn   = lineEl.querySelector('.line-mic-btn');

    if (!result.is_real) {
      lineEl.classList.add('rejected');
      if (statusEl) statusEl.textContent = '⚠️';
      if (micBtn)   micBtn.textContent = '🎙️';
    } else if (result.authenticated) {
      lineEl.classList.add('authenticated');
      if (statusEl) statusEl.textContent = '✅';
      if (micBtn)   micBtn.textContent = '✅';
    } else {
      lineEl.classList.add('rejected');
      if (statusEl) statusEl.textContent = '❌';
      if (micBtn)   micBtn.textContent = '🎙️';
    }
  }

  // ── Handle verify result ───────────────────────────────────
  function handleResult(lineEl, lineNum, data) {
    markLine(lineEl, data);
    updateStats(data);

    if (data.error) {
      writeToTerminal(`[LINE ${lineNum}] ⚠️  ${data.error}`, 'warn');
      return;
    }

    if (!data.is_real) {
      writeToTerminal(
        `[LINE ${lineNum}] ⚠️  SPOOF DETECTED | antispoof: ${data.antispoof_score?.toFixed(3)}`,
        'warn'
      );
      return;
    }

    const score = data.score?.toFixed(4) ?? 'N/A';
    const thr   = data.threshold ?? 'N/A';
    const dur   = data.vad_duration_s?.toFixed(2) ?? 'N/A';

    if (data.authenticated) {
      writeToTerminal(
        `[LINE ${lineNum}] ✅ AUTHENTICATED | score: ${score} | threshold: ${thr} | speech: ${dur}s`,
        'auth'
      );
    } else {
      writeToTerminal(
        `[LINE ${lineNum}] ❌ NOT ALLOWED   | score: ${score} | threshold: ${thr} | speech: ${dur}s`,
        'fail'
      );
    }
  }

  // ── Record + submit a line ─────────────────────────────────
  async function recordLine(lineEl) {
    const lineNum  = parseInt(lineEl.dataset.lineNum, 10);
    const lineText = lineEl.dataset.lineText;

    // Stop any existing recording
    if (recorder && recorder.isRecording) {
      recorder.stop();
      if (autoStopTimer) clearTimeout(autoStopTimer);
      return;
    }

    // Reset previous active line
    if (activeLineEl && activeLineEl !== lineEl) {
      activeLineEl.classList.remove('active', 'recording');
      const prevBtn = activeLineEl.querySelector('.line-mic-btn');
      if (prevBtn) prevBtn.textContent = '🎙️';
    }

    activeLineEl = lineEl;
    lineEl.classList.add('active', 'recording');
    lineEl.scrollIntoView({ behavior: 'smooth', block: 'center' });

    const micBtn = lineEl.querySelector('.line-mic-btn');
    if (micBtn) { micBtn.textContent = '⏹'; micBtn.classList.add('recording'); }

    writeToTerminal(`[LINE ${lineNum}] ● Recording...`, 'info');

    recorder = new VoiceRecorder({
      onStart: () => {
        autoStopTimer = setTimeout(() => {
          if (recorder && recorder.isRecording) recorder.stop();
        }, LINE_MAX_SECONDS * 1000);
      },
      onStop: async (blob) => {
        clearTimeout(autoStopTimer);
        if (micBtn) { micBtn.classList.remove('recording'); micBtn.textContent = '⏳'; }
        lineEl.classList.remove('recording');
        drawCanvas(0, new Uint8Array(48));

        writeToTerminal(`[LINE ${lineNum}] Processing...`, 'muted');

        const formData = new FormData();
        formData.append('audio', blob, `line_${lineNum}.webm`);
        formData.append('line_number', lineNum);
        formData.append('line_text', lineText);

        try {
          const res  = await fetch('/dashboard/verify-line', { method: 'POST', body: formData });
          const data = await res.json();
          handleResult(lineEl, lineNum, data);
        } catch (err) {
          writeToTerminal(`[LINE ${lineNum}] ❌ Network error: ${err.message}`, 'fail');
          lineEl.classList.remove('active', 'recording', 'authenticated', 'rejected');
          if (micBtn) micBtn.textContent = '🎙️';
        }
      },
      onVolumeChange: drawCanvas,
      onError: (err) => {
        writeToTerminal(`[LINE ${lineNum}] ❌ Mic error: ${err.message}`, 'fail');
        lineEl.classList.remove('active', 'recording');
        if (micBtn) { micBtn.textContent = '🎙️'; micBtn.classList.remove('recording'); }
      },
    });

    await recorder.start();
  }

  // ── Attach listeners to all mic buttons ───────────────────
  document.querySelectorAll('.line-mic-btn').forEach(btn => {
    btn.addEventListener('click', () => {
      const lineEl = btn.closest('.line-item');
      if (lineEl) recordLine(lineEl);
    });
  });

  // ── Clear terminal ─────────────────────────────────────────
  if (clearBtn) {
    clearBtn.addEventListener('click', () => {
      terminalBody.innerHTML = '';
      writeToTerminal('Terminal cleared.', 'muted');
    });
  }

  // ── Canvas size ────────────────────────────────────────────
  if (terminalCanvas) {
    const resize = () => {
      terminalCanvas.width  = terminalCanvas.offsetWidth;
      terminalCanvas.height = terminalCanvas.offsetHeight;
    };
    resize();
    window.addEventListener('resize', resize);
  }

  // ── Welcome message ────────────────────────────────────────
  writeToTerminal('VoiceAuth Dashboard ready. Click 🎙️ next to any line to verify.', 'info');
  writeToTerminal('Each line will show: ✅ AUTHENTICATED or ❌ NOT ALLOWED', 'muted');
})();
