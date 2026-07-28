const ui = new WebUI();
const preview = document.getElementById("preview");
const status = document.getElementById("status");
const warning = document.getElementById("mode-warning");
const cameraStatus = document.getElementById("camera-status");
const cameraLink = document.getElementById("camera-link");
const cameraOtp = document.getElementById("camera-otp");
const cameraQr = document.getElementById("camera-qr");
let protectedFrameDeadline;
let lastPairingUrl = "";

const insecureConditions = new Set([
  "M0_detection",
  "M1_blur",
  "M2_lorenz_only",
]);

function isReportedNumber(value) {
  return value !== null && value !== undefined && value !== "" && Number.isFinite(Number(value));
}

function failClosed() {
  clearTimeout(protectedFrameDeadline);
  preview.removeAttribute("src");
  preview.classList.add("unavailable");
  status.textContent = "Operational preview unavailable";
  document.getElementById("payload").textContent = "Unavailable; verify packet store separately";
}

function applyCondition(conditionValue) {
  const condition = String(conditionValue || "unknown");
  warning.hidden = !insecureConditions.has(condition);
  document.getElementById("condition").textContent = condition;
  document.getElementById("payload").textContent = insecureConditions.has(condition)
    ? "None: unauthenticated ablation"
    : "Not sent to this browser; verify packet store separately";
  return condition;
}

function renderCameraPairing(message) {
  const state = message || {};
  const cameraState = String(state.status || "disconnected");
  const clientName = String(state.client_name || "smartphone");
  const isStreaming = cameraState === "streaming";
  const isConnected = cameraState === "connected";

  cameraStatus.textContent = isStreaming
    ? `Streaming from ${clientName}`
    : isConnected
      ? `${clientName} connected; waiting for video`
      : "Camera disconnected; scan the current QR code";

  if (
    typeof state.secret !== "string"
    || typeof state.protocol !== "string"
    || typeof state.ip !== "string"
    || !isReportedNumber(state.port)
  ) {
    return;
  }

  const pairingUrl = new URL("https://cloud.arduino.cc/installmobileapp");
  pairingUrl.searchParams.set("otp", state.secret);
  pairingUrl.searchParams.set("protocol", state.protocol);
  pairingUrl.searchParams.set("ip", state.ip);
  pairingUrl.searchParams.set("port", String(state.port));

  cameraLink.href = pairingUrl.toString();
  cameraLink.hidden = false;
  cameraOtp.textContent = `Temporary pairing code: ${state.secret}`;
  cameraOtp.hidden = false;

  if (lastPairingUrl !== pairingUrl.toString()) {
    cameraQr.replaceChildren();
    new QRCode(cameraQr, {
      text: pairingUrl.toString(),
      width: 160,
      height: 160,
      colorDark: "#111827",
      colorLight: "#ffffff",
      correctLevel: QRCode.CorrectLevel.L,
    });
    lastPairingUrl = pairingUrl.toString();
  }
}

ui.on_connect(() => {
  status.textContent = "Connected; waiting for operational preview";
});

ui.on_disconnect(failClosed);

ui.on_message("experiment_state", (message) => {
  const state = message || {};
  const condition = applyCondition(state.condition);
  document.getElementById("run").textContent = state.run_id || "not reported";
  document.getElementById("auth-mode").textContent = state.authenticated_mode === true
    ? "AEAD requested"
    : state.authenticated_mode === false
      ? "No authentication (ablation)"
      : "not reported";
  document.getElementById("margin").textContent = isReportedNumber(state.bbox_margin_fraction)
    ? `${(100 * Number(state.bbox_margin_fraction)).toFixed(1)}% per side`
    : "not reported";
  if (!insecureConditions.has(condition) && typeof state.payload_status === "string") {
    document.getElementById("payload").textContent = state.payload_status;
  }
});

ui.on_message("camera_pairing", renderCameraPairing);
ui.on_message("camera_status", renderCameraPairing);

ui.on_message("pipeline_error", (message) => {
  failClosed();
  const code = message && message.error_code ? ` (${String(message.error_code)})` : "";
  status.textContent = `Pipeline failure${code}; preview removed and payload state invalidated`;
  document.getElementById("payload").textContent = "Unavailable after pipeline failure";
  if (message && message.condition) {
    applyCondition(message.condition);
    document.getElementById("payload").textContent = "Unavailable after pipeline failure";
  }
});

ui.on_message("protected_preview", (message) => {
  if (!message || typeof message.jpeg_b64 !== "string") {
    failClosed();
    return;
  }
  applyCondition(message.condition);
  preview.src = `data:image/jpeg;base64,${message.jpeg_b64}`;
  preview.classList.remove("unavailable");
  status.textContent = "Operational preview active (not the ROI packet)";
  document.getElementById("frame").textContent = message.frame_id ?? "unavailable";
  document.getElementById("run").textContent = message.run_id || "not reported";
  document.getElementById("rois").textContent = message.roi_count ?? "unavailable";
  document.getElementById("latency").textContent = isReportedNumber(message.protect_ms)
    ? `${Number(message.protect_ms).toFixed(3)} ms (Linux callback)`
    : "unavailable";
  clearTimeout(protectedFrameDeadline);
  protectedFrameDeadline = setTimeout(failClosed, 2500);
});

failClosed();
