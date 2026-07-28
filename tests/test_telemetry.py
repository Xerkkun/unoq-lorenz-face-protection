import threading

from unoq_lorenz.telemetry import TelemetryDispatcher, TelemetrySample


def test_dispatcher_forwards_sample_off_caller_thread():
    delivered = []
    ready = threading.Event()

    def sender(sample):
        delivered.append((sample, threading.current_thread().name))
        ready.set()

    dispatcher = TelemetryDispatcher(sender, capacity=2)
    sample = TelemetrySample(1, 2300, 2, True)
    assert dispatcher.submit(sample)
    assert ready.wait(1.0)
    dispatcher.close()
    assert delivered[0][0] == sample
    assert delivered[0][1] == "unoq-bridge-telemetry"
