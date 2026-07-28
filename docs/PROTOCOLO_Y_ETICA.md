# Protocolo, seguridad y ética

## Entregables mínimos

- pipeline ejecutable en UNO Q 4 GB;
- clips sintéticos publicables y, si se usan personas, consentimiento documentado;
- AEAD-only y chaos+AEAD con mismos nonces/datos de prueba sin reutilización real;
- test vectors, prueba de tamper y recuperación exacta;
- CSV de FPS/latencia/CPU/RAM y script de figuras;
- análisis de finite precision y ciclos cortos;
- modelo de amenaza y declaración de datos biométricos.

## Criterios de rechazo

- nonce reutilizado;
- descifrado acepta tag alterado;
- claves derivadas directamente de parámetros caóticos de baja entropía;
- se afirma seguridad por entropía, NPCR/UACI o NIST solamente;
- se publican rostros sin permiso o se retienen datos más allá del plan.
