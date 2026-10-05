/**
 * recorder.js — Reusable MediaRecorder wrapper for VoiceAuth
 *
 * Usage:
 *   const recorder = new VoiceRecorder({
 *     onStart: () => ...,
 *     onStop: (blob) => ...,
 *     onVolumeChange: (level, dataArray) => ...,
 *     onError: (err) => ...,
 *   });
 *   await recorder.start();
 *   recorder.stop();
 */

class VoiceRecorder {
  constructor(options = {}) {
    this.onStart         = options.onStart || null;
    this.onStop          = options.onStop  || null;
    this.onError         = options.onError || null;
    this.onVolumeChange  = options.onVolumeChange || null;

    this._mediaRecorder = null;
    this._stream        = null;
    this._chunks        = [];
    this._analyser      = null;
    this._audioCtx      = null;
    this._animFrameId   = null;
    this.mimeType       = this._bestMimeType();
  }

  _bestMimeType() {
    const candidates = [
      'audio/webm;codecs=opus',
      'audio/webm',
      'audio/ogg;codecs=opus',
      'audio/mp4',
    ];
    for (const t of candidates) {
      if (typeof MediaRecorder !== 'undefined' && MediaRecorder.isTypeSupported(t)) return t;
    }
    return '';
  }

  async start() {
    try {
      this._stream = await navigator.mediaDevices.getUserMedia({
        audio: {
          channelCount:    1,
          echoCancellation: true,
          noiseSuppression: false,  // handled server-side by DeepFilterNet
          autoGainControl:  true,
        },
        video: false,
      });

      // Set up AnalyserNode for volume visualiser
      this._audioCtx = new (window.AudioContext || window.webkitAudioContext)();
      const source   = this._audioCtx.createMediaStreamSource(this._stream);
      this._analyser = this._audioCtx.createAnalyser();
      this._analyser.fftSize = 256;
      source.connect(this._analyser);
      this._startVisualiser();

      this._chunks = [];
      this._mediaRecorder = new MediaRecorder(this._stream, {
        mimeType:          this.mimeType,
        audioBitsPerSecond: 128000,
      });

      this._mediaRecorder.ondataavailable = (e) => {
        if (e.data && e.data.size > 0) this._chunks.push(e.data);
      };

      this._mediaRecorder.onstop = () => {
        this._stopVisualiser();
        const blob = new Blob(this._chunks, { type: this.mimeType || 'audio/webm' });
        if (this.onStop) this.onStop(blob);
      };

      this._mediaRecorder.start(100);  // 100 ms timeslices
      if (this.onStart) this.onStart();

    } catch (err) {
      if (this.onError) this.onError(err);
    }
  }

  stop() {
    if (this._mediaRecorder && this._mediaRecorder.state !== 'inactive') {
      this._mediaRecorder.stop();
    }
    if (this._stream) {
      this._stream.getTracks().forEach(t => t.stop());
    }
    if (this._audioCtx && this._audioCtx.state !== 'closed') {
      this._audioCtx.close();
    }
  }

  get isRecording() {
    return !!(this._mediaRecorder && this._mediaRecorder.state === 'recording');
  }

  _startVisualiser() {
    const bufLen  = this._analyser.frequencyBinCount;
    const data    = new Uint8Array(bufLen);

    const tick = () => {
      this._animFrameId = requestAnimationFrame(tick);
      this._analyser.getByteFrequencyData(data);
      // Use the lower 64 bins (voice frequencies)
      const slice = data.slice(0, 64);
      const avg   = slice.reduce((s, v) => s + v, 0) / slice.length;
      if (this.onVolumeChange) this.onVolumeChange(avg / 255, data);
    };
    tick();
  }

  _stopVisualiser() {
    if (this._animFrameId) {
      cancelAnimationFrame(this._animFrameId);
      this._animFrameId = null;
    }
    if (this.onVolumeChange) this.onVolumeChange(0, new Uint8Array(128));
  }
}

// Expose globally
window.VoiceRecorder = VoiceRecorder;
