# UNO Q Lorenz software evidence package v3

This is a source-and-evidence package for independent review of the Arduino
UNO Q Lorenz-assisted authenticated facial-ROI prototype.

Evidence boundary:

- `data/software_verification_*` contains deterministic development-host
  verification only; it is not Arduino UNO Q performance evidence.
- `data/board/run_manifest_template.json` is an unfilled protocol template.
- No physical-board metrics, raw video, face images, participant data, consent
  forms, master keys, private run contracts, caches, bytecode, or environments
  are included.
- The recoverable M3/M4 artifact is the authenticated packet bundle produced at
  run time; operational preview JPEGs are not recovery evidence.

Start with `README.md` and either
`docs/MANUAL_REPRODUCCION_ESTUDIANTES.md` or
`docs/STUDENT_REPRODUCTION_MANUAL.md`. The theory and registered experiment
contract remain in `docs/TEORIA_Y_DISENO_SOFTWARE.md` and
`docs/EXPERIMENT_PROTOCOL.md`. Run the local verification commands documented
in `README.md` and review `MANIFEST.sha256` before using the contents.

`MANIFEST.sha256` hashes every packaged file except itself, avoiding a circular
digest. The archive uses sorted paths and a fixed ZIP timestamp so identical
inputs produce identical bytes.
