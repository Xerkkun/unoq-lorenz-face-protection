#include <Arduino_RouterBridge.h>

// These values are forwarded by the Linux application. The STM32U585 does not
// measure protection latency or detector throughput in this sketch.
struct ForwardedMetric {
  unsigned long frameId;
  unsigned long linuxProtectUs;
  int roiCount;
  bool authenticatedMode;
};

constexpr size_t kMetricBufferCapacity = 32;
ForwardedMetric metricBuffer[kMetricBufferCapacity];

volatile unsigned long receivedFrames = 0;
volatile unsigned long authenticatedMessages = 0;
volatile unsigned long unauthenticatedMessages = 0;
volatile unsigned long invalidMessages = 0;
volatile unsigned long overwrittenMessages = 0;
volatile unsigned long lastFrameId = 0;
volatile unsigned long lastLinuxProtectUs = 0;
volatile int lastRoiCount = 0;
volatile bool lastAuthenticatedMode = false;
volatile size_t metricBufferHead = 0;
volatile size_t metricBufferCount = 0;

void record_metrics(
  int frameId,
  int linuxProtectUs,
  int roiCount,
  bool authenticatedMode
) {
  if (frameId < 0 || linuxProtectUs < 0 || roiCount < 0) {
    invalidMessages++;
    return;
  }

  const size_t writeIndex = metricBufferHead;
  metricBuffer[writeIndex].frameId = static_cast<unsigned long>(frameId);
  metricBuffer[writeIndex].linuxProtectUs =
    static_cast<unsigned long>(linuxProtectUs);
  metricBuffer[writeIndex].roiCount = roiCount;
  metricBuffer[writeIndex].authenticatedMode = authenticatedMode;
  metricBufferHead = (writeIndex + 1) % kMetricBufferCapacity;
  if (metricBufferCount < kMetricBufferCapacity) {
    metricBufferCount++;
  } else {
    overwrittenMessages++;
  }

  receivedFrames++;
  lastFrameId = static_cast<unsigned long>(frameId);
  lastLinuxProtectUs = static_cast<unsigned long>(linuxProtectUs);
  lastRoiCount = roiCount;
  lastAuthenticatedMode = authenticatedMode;
  if (authenticatedMode) {
    authenticatedMessages++;
  } else {
    unauthenticatedMessages++;
  }
  digitalWrite(LED_BUILTIN, authenticatedMode ? HIGH : LOW);
}

void print_forwarded_status() {
  noInterrupts();
  const unsigned long frames = receivedFrames;
  const unsigned long authenticated = authenticatedMessages;
  const unsigned long unauthenticated = unauthenticatedMessages;
  const unsigned long invalid = invalidMessages;
  const unsigned long overwritten = overwrittenMessages;
  const unsigned long frameId = lastFrameId;
  const unsigned long linuxProtectUs = lastLinuxProtectUs;
  const int roiCount = lastRoiCount;
  const bool authenticatedMode = lastAuthenticatedMode;
  const size_t buffered = metricBufferCount;
  interrupts();

  Serial.print("{\"type\":\"forwarded_metrics_status\",\"received_messages\":");
  Serial.print(frames);
  Serial.print(",\"authenticated_mode_messages\":");
  Serial.print(authenticated);
  Serial.print(",\"unauthenticated_mode_messages\":");
  Serial.print(unauthenticated);
  Serial.print(",\"invalid_messages\":");
  Serial.print(invalid);
  Serial.print(",\"buffered_messages\":");
  Serial.print(buffered);
  Serial.print(",\"overwritten_messages\":");
  Serial.print(overwritten);
  Serial.print(",\"last_frame_id\":");
  Serial.print(frameId);
  Serial.print(",\"last_linux_reported_protect_us\":");
  Serial.print(linuxProtectUs);
  Serial.print(",\"last_roi_count\":");
  Serial.print(roiCount);
  Serial.print(",\"last_authenticated_mode\":");
  Serial.print(authenticatedMode ? "true" : "false");
  Serial.println("}");
}

void setup() {
  Serial.begin(115200);
  pinMode(LED_BUILTIN, OUTPUT);
  digitalWrite(LED_BUILTIN, LOW);
  Bridge.begin();
  Bridge.provide("record_metrics", record_metrics);
}

void loop() {
  static unsigned long lastStatusMs = 0;
  const unsigned long nowMs = millis();
  if (nowMs - lastStatusMs >= 1000) {
    lastStatusMs = nowMs;
    print_forwarded_status();
  }
  delay(10);
}
