const chatBox = document.getElementById("chatBox");
const chatInput = document.getElementById("chatInput");
const sendBtn = document.getElementById("sendBtn");
const recordBtn = document.getElementById("recordBtn");
const recorderPanel = document.getElementById("recorderPanel");
const recordingState = document.getElementById("recordingState");
const recordingTimer = document.getElementById("recordingTimer");
const recordingWave = document.getElementById("recordingWave");
const recPauseBtn = document.getElementById("recPauseBtn");
const recResumeBtn = document.getElementById("recResumeBtn");
const recPreviewBtn = document.getElementById("recPreviewBtn");
const recSendBtn = document.getElementById("recSendBtn");
const recAbortBtn = document.getElementById("recAbortBtn");
const recPreviewAudio = document.getElementById("recPreviewAudio");

let mediaRecorder = null;
let chunks = [];
let recordingStream = null;
let recordingBlob = null;
let recordingMimeType = "audio/webm";
let recordingStartAt = 0;
let pausedAccumulatedMs = 0;
let pauseStartAt = 0;
let timerIntervalId = null;
let audioContext = null;
let analyser = null;
let analyserData = null;
let waveAnimationId = null;
let abortRequested = false;
let previewUrl = "";

const ttsButtonState = new WeakMap();
let activeTtsAudio = null;
let activeTtsButton = null;

function appendSystemMessage(text) {
  appendBubble("assistant", text);
}

async function parseErrorResponse(response) {
  const contentType = response.headers.get("content-type") || "";
  try {
    if (contentType.includes("application/json")) {
      const payload = await response.json();
      return payload.message || `Error HTTP ${response.status}`;
    }
    const rawText = await response.text();
    if (!rawText) {
      return `Error HTTP ${response.status}`;
    }
    return rawText.slice(0, 240);
  } catch (_) {
    return `Error HTTP ${response.status}`;
  }
}

async function parseJsonSafe(response) {
  const contentType = response.headers.get("content-type") || "";
  if (!contentType.includes("application/json")) {
    return {
      ok: false,
      message: await parseErrorResponse(response),
    };
  }
  try {
    return await response.json();
  } catch (_) {
    return {
      ok: false,
      message: `Respuesta JSON inválida (HTTP ${response.status})`,
    };
  }
}

function appendBubble(role, text) {
  const article = document.createElement("article");
  article.className = `bubble bubble-${role}`;

  const paragraph = document.createElement("p");
  paragraph.textContent = text;
  article.appendChild(paragraph);

  if (role === "assistant") {
    const listen = document.createElement("button");
    listen.className = "listen-btn";
    listen.type = "button";
    setListenButtonVisualState(listen, "idle");
    listen.addEventListener("click", async () => {
      await toggleTTSPlayback(listen, text, article);
    });
    article.appendChild(listen);
  }

  chatBox.appendChild(article);
  chatBox.scrollTop = chatBox.scrollHeight;
}

function setListenButtonVisualState(button, state) {
  if (state === "loading") {
    button.textContent = "Cargando...";
    button.disabled = true;
    return;
  }
  button.disabled = false;
  if (state === "playing") {
    button.textContent = "Pausar";
  } else if (state === "paused") {
    button.textContent = "Reanudar";
  } else {
    button.textContent = "Escuchar";
  }
}

function ensureBubbleAudioPlayer(article) {
  let player = article.querySelector("audio.tts-audio");
  if (!player) {
    player = document.createElement("audio");
    player.className = "tts-audio";
    player.controls = true;
    player.preload = "none";
    article.appendChild(player);
  }
  return player;
}

function stopCurrentTTSIfNeeded(nextButton, nextAudio) {
  if (activeTtsAudio && activeTtsAudio !== nextAudio) {
    activeTtsAudio.pause();
  }
  if (activeTtsButton && activeTtsButton !== nextButton) {
    setListenButtonVisualState(activeTtsButton, "paused");
  }
}

async function toggleTTSPlayback(button, text, article) {
  const existing = ttsButtonState.get(button);
  if (existing?.state === "playing" && existing.audio) {
    existing.audio.pause();
    return;
  }
  if (existing?.state === "paused" && existing.audio) {
    stopCurrentTTSIfNeeded(button, existing.audio);
    await existing.audio.play();
    return;
  }
  if (existing?.state === "loading") {
    return;
  }

  try {
    setListenButtonVisualState(button, "loading");
    ttsButtonState.set(button, { state: "loading", audio: null, url: "" });

    const response = await fetch("/api/tts", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text }),
    });
    if (!response.ok) {
      const errorMessage = await parseErrorResponse(response);
      setListenButtonVisualState(button, "idle");
      ttsButtonState.set(button, { state: "idle", audio: null, url: "" });
      appendSystemMessage(`No se pudo reproducir audio: ${errorMessage}`);
      return;
    }

    const blob = await response.blob();
    const player = ensureBubbleAudioPlayer(article);
    const url = URL.createObjectURL(blob);
    player.src = url;

    const previous = ttsButtonState.get(button);
    if (previous?.url) {
      URL.revokeObjectURL(previous.url);
    }

    player.onplay = () => {
      stopCurrentTTSIfNeeded(button, player);
      activeTtsAudio = player;
      activeTtsButton = button;
      setListenButtonVisualState(button, "playing");
      ttsButtonState.set(button, { state: "playing", audio: player, url });
    };

    player.onpause = () => {
      if (player.ended) {
        setListenButtonVisualState(button, "idle");
        ttsButtonState.set(button, { state: "idle", audio: player, url });
      } else {
        setListenButtonVisualState(button, "paused");
        ttsButtonState.set(button, { state: "paused", audio: player, url });
      }
    };

    player.onended = () => {
      setListenButtonVisualState(button, "idle");
      ttsButtonState.set(button, { state: "idle", audio: player, url });
      if (activeTtsAudio === player) {
        activeTtsAudio = null;
      }
      if (activeTtsButton === button) {
        activeTtsButton = null;
      }
    };

    stopCurrentTTSIfNeeded(button, player);
    await player.play();
  } catch (error) {
    setListenButtonVisualState(button, "idle");
    ttsButtonState.set(button, { state: "idle", audio: null, url: "" });
    appendSystemMessage(`Error al reproducir audio: ${error?.message || "error desconocido"}`);
  }
}

async function sendMessage() {
  try {
    const message = chatInput.value.trim();
    if (!message) return;

    appendBubble("user", message);
    chatInput.value = "";

    sendBtn.disabled = true;

    const response = await fetch("/api/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ message }),
    });
    const payload = await parseJsonSafe(response);
    if (!payload.ok) {
      appendBubble("assistant", payload.message || "No se pudo procesar tu mensaje.");
      return;
    }
    appendBubble("assistant", payload.reply);
  } catch (error) {
    const detail = error?.message || "error desconocido";
    appendSystemMessage(
      `No se pudo enviar el mensaje (${detail}). Verifica que la web esté en http://127.0.0.1:5000 y vuelve a iniciar sesión.`
    );
  } finally {
    sendBtn.disabled = false;
  }
}

function formatTimer(totalMs) {
  const totalSeconds = Math.max(0, Math.floor(totalMs / 1000));
  const minutes = String(Math.floor(totalSeconds / 60)).padStart(2, "0");
  const seconds = String(totalSeconds % 60).padStart(2, "0");
  return `${minutes}:${seconds}`;
}

function currentRecordingElapsedMs() {
  if (!recordingStartAt) {
    return 0;
  }
  if (mediaRecorder && mediaRecorder.state === "paused") {
    return pauseStartAt - recordingStartAt - pausedAccumulatedMs;
  }
  return Date.now() - recordingStartAt - pausedAccumulatedMs;
}

function startRecordingTimer() {
  if (timerIntervalId) {
    clearInterval(timerIntervalId);
  }
  timerIntervalId = setInterval(() => {
    if (recordingTimer) {
      recordingTimer.textContent = formatTimer(currentRecordingElapsedMs());
    }
  }, 250);
}

function stopRecordingTimer() {
  if (timerIntervalId) {
    clearInterval(timerIntervalId);
    timerIntervalId = null;
  }
}

function clearPreviewUrl() {
  if (previewUrl) {
    URL.revokeObjectURL(previewUrl);
    previewUrl = "";
  }
}

function resetRecorderUi() {
  recorderPanel?.classList.add("hidden");
  if (recordingState) {
    recordingState.textContent = "Grabando...";
  }
  if (recordingTimer) {
    recordingTimer.textContent = "00:00";
  }
  if (recPreviewAudio) {
    recPreviewAudio.pause();
    recPreviewAudio.classList.add("hidden");
    recPreviewAudio.removeAttribute("src");
    recPreviewAudio.load();
  }
  clearPreviewUrl();
  recordBtn.textContent = "Grabar Audio";
  recPauseBtn.disabled = true;
  recResumeBtn.disabled = true;
  recPreviewBtn.disabled = true;
  recPreviewBtn.textContent = "Reproducir";
  recSendBtn.disabled = true;
  recAbortBtn.disabled = true;
}

function drawWave() {
  if (!recordingWave) {
    return;
  }
  const context = recordingWave.getContext("2d");
  if (!context) {
    return;
  }

  context.clearRect(0, 0, recordingWave.width, recordingWave.height);
  context.fillStyle = "#f4ebff";
  context.fillRect(0, 0, recordingWave.width, recordingWave.height);

  if (!analyser || !analyserData) {
    waveAnimationId = requestAnimationFrame(drawWave);
    return;
  }

  analyser.getByteFrequencyData(analyserData);
  const barCount = 48;
  const step = Math.max(1, Math.floor(analyserData.length / barCount));
  const barWidth = recordingWave.width / barCount;

  for (let i = 0; i < barCount; i += 1) {
    const value = analyserData[i * step] / 255;
    const barHeight = Math.max(4, value * (recordingWave.height - 10));
    const x = i * barWidth;
    const y = (recordingWave.height - barHeight) / 2;
    context.fillStyle = "#7f3fe0";
    context.fillRect(x + 1, y, barWidth - 2, barHeight);
  }

  waveAnimationId = requestAnimationFrame(drawWave);
}

function startWave(stream) {
  stopWave();
  try {
    const Ctx = window.AudioContext || window.webkitAudioContext;
    if (!Ctx) {
      return;
    }
    audioContext = new Ctx();
    const source = audioContext.createMediaStreamSource(stream);
    analyser = audioContext.createAnalyser();
    analyser.fftSize = 512;
    analyserData = new Uint8Array(analyser.frequencyBinCount);
    source.connect(analyser);
    drawWave();
  } catch (_) {
    analyser = null;
    analyserData = null;
  }
}

function stopWave() {
  if (waveAnimationId) {
    cancelAnimationFrame(waveAnimationId);
    waveAnimationId = null;
  }
  if (audioContext) {
    audioContext.close().catch(() => {});
    audioContext = null;
  }
  analyser = null;
  analyserData = null;
}

function stopRecordingTracks() {
  if (recordingStream) {
    recordingStream.getTracks().forEach((track) => track.stop());
    recordingStream = null;
  }
}

function chooseRecordingMimeType() {
  if (typeof MediaRecorder === "undefined" || !MediaRecorder.isTypeSupported) {
    return "audio/webm";
  }
  const candidates = ["audio/webm;codecs=opus", "audio/webm", "audio/mp4"];
  for (const mime of candidates) {
    if (MediaRecorder.isTypeSupported(mime)) {
      return mime;
    }
  }
  return "audio/webm";
}

function beginRecordingUi() {
  recorderPanel?.classList.remove("hidden");
  if (recordingState) {
    recordingState.textContent = "Grabando...";
  }
  recPauseBtn.disabled = false;
  recResumeBtn.disabled = true;
  recPreviewBtn.disabled = true;
  recSendBtn.disabled = true;
  recAbortBtn.disabled = false;
  recordBtn.textContent = "Finalizar";
}

function markRecordingPaused() {
  if (recordingState) {
    recordingState.textContent = "Grabacion en pausa";
  }
  recPauseBtn.disabled = true;
  recResumeBtn.disabled = false;
}

function markRecordingResumed() {
  if (recordingState) {
    recordingState.textContent = "Grabando...";
  }
  recPauseBtn.disabled = false;
  recResumeBtn.disabled = true;
}

function markRecordingReady() {
  if (recordingState) {
    recordingState.textContent = "Audio listo para enviar";
  }
  recPauseBtn.disabled = true;
  recResumeBtn.disabled = true;
  recPreviewBtn.disabled = false;
  recPreviewBtn.textContent = "Reproducir";
  recSendBtn.disabled = false;
  recAbortBtn.disabled = false;
  recordBtn.textContent = "Nueva grabacion";
}

async function startOrFinishRecording() {
  if (mediaRecorder && (mediaRecorder.state === "recording" || mediaRecorder.state === "paused")) {
    if (recordingState) {
      recordingState.textContent = "Procesando audio...";
    }
    mediaRecorder.stop();
    return;
  }

  chunks = [];
  recordingBlob = null;
  abortRequested = false;
  pausedAccumulatedMs = 0;
  pauseStartAt = 0;
  stopRecordingTimer();
  clearPreviewUrl();
  if (recPreviewAudio) {
    recPreviewAudio.pause();
    recPreviewAudio.classList.add("hidden");
    recPreviewAudio.removeAttribute("src");
    recPreviewAudio.load();
  }

  if (!navigator.mediaDevices?.getUserMedia) {
    appendSystemMessage("Tu navegador no soporta grabación de audio.");
    return;
  }

  if (typeof MediaRecorder === "undefined") {
    appendSystemMessage("MediaRecorder no está disponible en este navegador.");
    return;
  }

  let stream;
  try {
    stream = await navigator.mediaDevices.getUserMedia({ audio: true });
  } catch (error) {
    appendSystemMessage("No se pudo acceder al micrófono. Revisa permisos del navegador.");
    return;
  }

  recordingStream = stream;
  recordingMimeType = chooseRecordingMimeType();

  try {
    mediaRecorder = new MediaRecorder(stream, { mimeType: recordingMimeType });
  } catch (_) {
    mediaRecorder = new MediaRecorder(stream);
    recordingMimeType = mediaRecorder.mimeType || "audio/webm";
  }

  beginRecordingUi();
  recordingStartAt = Date.now();
  if (recordingTimer) {
    recordingTimer.textContent = "00:00";
  }
  startRecordingTimer();
  startWave(stream);

  mediaRecorder.ondataavailable = (event) => {
    if (event.data.size > 0) {
      chunks.push(event.data);
    }
  };

  mediaRecorder.onpause = () => {
    pauseStartAt = Date.now();
    markRecordingPaused();
  };

  mediaRecorder.onresume = () => {
    if (pauseStartAt) {
      pausedAccumulatedMs += Date.now() - pauseStartAt;
      pauseStartAt = 0;
    }
    markRecordingResumed();
  };

  mediaRecorder.onstop = async () => {
    stopRecordingTimer();
    stopWave();
    stopRecordingTracks();

    if (abortRequested) {
      mediaRecorder = null;
      chunks = [];
      recordingBlob = null;
      resetRecorderUi();
      return;
    }

    try {
      recordingBlob = new Blob(chunks, { type: recordingMimeType || "audio/webm" });
      if (!recordingBlob.size) {
        appendSystemMessage("No se detectó audio grabado.");
        resetRecorderUi();
        return;
      }

      clearPreviewUrl();
      previewUrl = URL.createObjectURL(recordingBlob);
      if (recPreviewAudio) {
        recPreviewAudio.src = previewUrl;
        recPreviewAudio.classList.remove("hidden");
      }
      markRecordingReady();
    } catch (error) {
      appendSystemMessage(`Error procesando audio: ${error?.message || "error desconocido"}`);
      resetRecorderUi();
    }

    mediaRecorder = null;
  };

  mediaRecorder.start();
}

function pauseRecording() {
  if (mediaRecorder && mediaRecorder.state === "recording") {
    mediaRecorder.pause();
  }
}

function resumeRecording() {
  if (mediaRecorder && mediaRecorder.state === "paused") {
    mediaRecorder.resume();
  }
}

function abortRecording() {
  recPreviewAudio?.pause();
  clearPreviewUrl();

  if (mediaRecorder && (mediaRecorder.state === "recording" || mediaRecorder.state === "paused")) {
    abortRequested = true;
    mediaRecorder.stop();
    return;
  }

  stopRecordingTimer();
  stopWave();
  stopRecordingTracks();
  chunks = [];
  recordingBlob = null;
  mediaRecorder = null;
  resetRecorderUi();
}

function togglePreviewPlayback() {
  if (!recPreviewAudio || recPreviewAudio.classList.contains("hidden")) {
    return;
  }
  if (recPreviewAudio.paused) {
    recPreviewAudio.play().catch(() => {});
  } else {
    recPreviewAudio.pause();
  }
}

async function sendRecordedAudio() {
  if (!recordingBlob || !recordingBlob.size) {
    appendSystemMessage("No hay audio para enviar.");
    return;
  }

  try {
    recSendBtn.disabled = true;
    recAbortBtn.disabled = true;
    if (recordingState) {
      recordingState.textContent = "Transcribiendo...";
    }

    const formData = new FormData();
    formData.append("audio", recordingBlob, "recording.webm");

    const sttResponse = await fetch("/api/stt", {
      method: "POST",
      body: formData,
    });

    const sttPayload = await parseJsonSafe(sttResponse);

    if (!sttPayload.ok) {
      appendBubble("assistant", sttPayload.message || "No se pudo procesar el audio.");
      recSendBtn.disabled = false;
      recAbortBtn.disabled = false;
      if (recordingState) {
        recordingState.textContent = "Audio listo para enviar";
      }
      return;
    }

    chatInput.value = sttPayload.text;
    await sendMessage();
    abortRecording();
  } catch (error) {
    appendSystemMessage(`Error procesando audio: ${error?.message || "error desconocido"}`);
    recSendBtn.disabled = false;
    recAbortBtn.disabled = false;
    if (recordingState) {
      recordingState.textContent = "Audio listo para enviar";
    }
  }
}

sendBtn?.addEventListener("click", sendMessage);
chatInput?.addEventListener("keydown", (event) => {
  if (event.key === "Enter") {
    event.preventDefault();
    sendMessage();
  }
});
recordBtn?.addEventListener("click", startOrFinishRecording);
recPauseBtn?.addEventListener("click", pauseRecording);
recResumeBtn?.addEventListener("click", resumeRecording);
recPreviewBtn?.addEventListener("click", togglePreviewPlayback);
recSendBtn?.addEventListener("click", sendRecordedAudio);
recAbortBtn?.addEventListener("click", abortRecording);

recPreviewAudio?.addEventListener("play", () => {
  recPreviewBtn.textContent = "Pausar preview";
});
recPreviewAudio?.addEventListener("pause", () => {
  if (!recPreviewAudio.ended) {
    recPreviewBtn.textContent = "Reproducir";
  }
});
recPreviewAudio?.addEventListener("ended", () => {
  recPreviewBtn.textContent = "Reproducir";
});

document.querySelectorAll(".listen-btn").forEach((button) => {
  button.addEventListener("click", async () => {
    const text = button.getAttribute("data-text") || "";
    const article = button.closest("article");
    if (!article) {
      return;
    }
    await toggleTTSPlayback(button, text, article);
  });
});
