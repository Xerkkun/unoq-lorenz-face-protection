# Third-party browser helpers

`assets/libs/arduino.js` is copied without modification from Arduino's
`app-bricks-examples` repository, example
`examples/platform_unoq/video-face-detection`, inspected on 2026-07-20.  Its
source header identifies Arduino s.r.l. and affiliates as copyright holders
and applies the Mozilla Public License 2.0.

`assets/libs/socket.io.min.js` is the Socket.IO browser client distributed by
the same official example.  Its embedded header identifies Socket.IO
contributors and the MIT license.

`assets/libs/qrcode.min.js` is copied without modification from Arduino's
official `Detect Objects on Smartphone Camera` example exported from Arduino
App CLI 0.11.1 on 2026-07-28. It renders only the temporary Arduino IoT Remote
pairing URI and is not involved in ROI protection.

Upstream locations:

- https://github.com/arduino/app-bricks-examples
- https://github.com/socketio/socket.io-client

These files support the WebUI transport only.  They are not part of the Lorenz
transform, AEAD implementation, or experimental measurements.
