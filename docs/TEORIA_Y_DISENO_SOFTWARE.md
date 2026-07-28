# Teoría y diseño de software: Arduino UNO Q, Lorenz y protección de ROI faciales

## 1. Pregunta de investigación

El trabajo compara, sobre Arduino UNO Q, el costo y el comportamiento funcional
de cinco rutas posteriores a la detección de un rostro. La pregunta principal
no es si «Lorenz cifra», sino si una transformación reversible derivada de
Lorenz aporta algún efecto medible cuando se coloca antes de un mecanismo
criptográfico estándar, y cuál es su costo frente a una línea base AEAD.

La afirmación de seguridad se limita a ChaCha20-Poly1305 y al contrato de claves,
nonces, datos asociados y rechazo de repeticiones. La etapa Lorenz es una
variable experimental. Entropía, histogramas, NPCR, UACI o apariencia de ruido
no demuestran confidencialidad ni integridad.

## 2. Modelo dinámico

El sistema clásico de Lorenz es

\[
\dot{x}=\sigma(y-x),\qquad
\dot{y}=x(\rho-z)-y,\qquad
\dot{z}=xy-\beta z,
\]

con \(\sigma=10\), \(\rho=28\) y \(\beta=8/3\). La implementación registrada
emplea RK4 en `float64`, paso fijo \(h=0.005\), un transitorio de 2048 pasos y
512 muestras para obtener un resumen reproducible de trayectoria.

La versión `lorenz-rk4-sha256-pcg64-v2` no integra una muestra por cada byte de
la imagen. Integra una trayectoria corta y de costo fijo una vez al construir
el protector de la corrida, cuantiza sus estados con escala \(10^9\) y calcula
SHA-256. Ese resumen,
la longitud del ROI, una clave separada y el nonce alimentan HKDF-SHA-256. Un
generador PCG64 expande después la semilla para construir:

- una permutación de los bytes del ROI;
- una máscara de ocho bits por posición.

PCG64 se usa para expansión determinista y rápida, no como frontera
criptográfica. La salida completa permanece dentro del sobre AEAD. Cambiar el
integrador, el paso, el transitorio, la cuantización o la expansión requiere un
nuevo identificador de perfil: no puede hacerse silenciosamente. La versión de
NumPy y la API exacta `Generator(PCG64).permutation+integers` también forman
parte del perfil autenticado.

## 3. Transformación reversible

Sea \(P=(p_0,\ldots,p_{n-1})\) la representación contigua en bytes del ROI,
\(\pi\) una permutación y \(m_i\) la máscara. La transformación es

\[
q_i=p_{\pi_i}\oplus m_i,
\]

y la inversa coloca \(q_i\oplus m_i\) de nuevo en la posición \(\pi_i\). La
permutación y la máscara dependen de la clave de agenda, el nonce, la longitud y
el perfil numérico. El resultado debe recuperarse byte por byte; una imagen
«parecida» no satisface el contrato.

## 4. Envoltura criptográfica

De una clave maestra aleatoria de 32 bytes se derivan, con dominios HKDF
distintos, una clave para ChaCha20-Poly1305 y otra para la agenda Lorenz. Cada
paquete usa un nonce de 96 bits formado por un prefijo aleatorio de 64 bits y un
contador de 32 bits. Además:

- cada corrida exige un `run_id` nuevo y una clave maestra nueva;
- el contador se asigna bajo bloqueo y no puede desbordarse;
- el identificador de paquete coincide con el contador asignado;
- el receptor autentica antes de reconstruir el ROI;
- el receptor rechaza paquetes ya aceptados en la misma corrida;
- el perfil Lorenz, el algoritmo AEAD y el perfil KDF forman parte de los datos
  asociados autenticados.

El paquete recuperable contiene, como mínimo, `run_id`, `packet_id`, nonce,
coordenadas y forma del ROI, identificador de cuadro de la aplicación,
bandera `use_lorenz`, perfiles de algoritmo y `ciphertext || tag`. El JPEG del navegador
es sólo una vista comprimida; nunca sustituye el paquete recuperable.

El rechazo de replay no es una propiedad automática de ChaCha20-Poly1305. Lo
aporta un receptor con estado que conserva las identidades y nonces ya
aceptados durante la vida de la clave de corrida.

## 5. Reparto de trabajo en Arduino UNO Q

### QRB2210 / Debian

- recibe el JPEG y las cajas del Brick de detección;
- decodifica y expande las cajas con un margen registrado;
- extrae los ROI;
- ejecuta M0--M4;
- en el código actual, guarda atómicamente los paquetes recuperables en M3/M4;
- genera un JPEG de vista protegida;
- escribe métricas con unidades explícitas;
- encola telemetría compacta para Bridge sin bloquear el callback.

### STM32U585

- recibe identificador local de cuadro, tiempo de protección reportado por
  Linux, número de ROI y si la condición es autenticada;
- conserva contadores/estado compacto para diagnóstico;
- no recibe imágenes, no ejecuta la detección y no mide por sí mismo la
  latencia de inferencia.

Esta asignación aprovecha la heterogeneidad de UNO Q sin presentar al
microcontrolador como raíz de confianza o acelerador criptográfico cuando aún
no se ha demostrado ninguna de esas funciones.

## 6. Condiciones experimentales

| ID | Ruta | Interpretación |
|---|---|---|
| M0 | detección, sin modificar ROI | línea base de callback; no protege |
| M1 | desenfoque | línea base visual irreversible; no autentica |
| M2 | Lorenz solamente | ablación reversible de laboratorio; no autentica |
| M3 | AEAD del ROI original | línea base criptográfica |
| M4 | Lorenz y después AEAD | composición propuesta para comparar |

M0--M2 requieren una habilitación explícita y la WebUI debe mostrarlas con una
advertencia roja. Sólo M3 y M4 producen paquetes autenticados recuperables.

## 7. Flujo de software

```text
Brick de detección
  -> JPEG y cajas disponibles para el callback
  -> decodificación OpenCV
  -> expansión y recorte de cajas
  -> ejecución de la condición M0--M4
       -> M3/M4: paquete AEAD recuperable
       -> todas: vista de demostración según la condición
  -> M3/M4: almacenamiento atómico del paquete antes de declarar éxito
  -> codificación JPEG de la vista
  -> mensaje WebUI marcado como preview no recuperable
  -> fila CSV con tiempos, tamaños y contexto de corrida
  -> cola acotada de telemetría hacia STM32U585
```

Si falla el almacenamiento en M3/M4, la aplicación invalida el estado de
payload y ordena retirar el preview del navegador.

El Brick oficial entrega la clasificación y el último preview por rutas
asíncronas, sin un identificador fuente común. Por ello, el `frame_id` del
prototipo identifica el callback de la aplicación, no prueba por sí solo que la
caja y el JPEG correspondan al mismo cuadro capturado. Esta alineación debe
medirse con una fuente sincronizada o con un Brick instrumentado.

## 8. Variables de ejecución

Antes de iniciar una corrida se deben fijar, como mínimo:

```text
UNOQ_MASTER_KEY_B64       clave aleatoria opcional de 32 bytes, nunca versionada
UNOQ_MASTER_KEY_FILE      archivo privado alternativo; no usar junto con B64
UNOQ_RUN_ID               identificador único de la corrida
UNOQ_CONDITION            M0_detection ... M4_lorenz_aead
UNOQ_SCENE                stationary, motion o illumination
UNOQ_BBOX_MARGIN_FRACTION margen relativo alrededor de cada caja
UNOQ_METRICS_CSV          CSV exclusivo de esa corrida
UNOQ_PACKET_DIR           raíz privada para paquetes M3/M4
```

Para M0--M2 también se requiere:

```text
UNOQ_ALLOW_INSECURE_ABLATION=1
```

Si no se proporciona una clave, el adaptador genera una nueva en el directorio
privado indicado por `UNOQ_SECRET_DIR`; el archivo se excluye del material
publicable. No se debe reutilizar una clave ni un directorio de corrida después
de reiniciar el proceso. Tampoco se deben guardar claves, video original, nombres de
participantes o consentimientos dentro del paquete publicable.

## 9. Orden recomendado de implementación y prueba

1. Ejecutar las pruebas unitarias y la verificación sintética en PC.
2. Abrir la aplicación con una imagen sintética y confirmar que la WebUI del
   experimento no incrusta ni enlaza el stream crudo.
3. Ejecutar M3 y reconstruir cada ROI desde el JSON almacenado, no desde el
   JPEG mostrado.
4. Alterar por separado ciphertext, tag, AAD, nonce, clave, perfil y contador;
   todos deben ser rechazados.
5. Repetir un paquete válido; el receptor debe rechazar el replay.
6. Ejecutar M4 y comprobar recuperación exacta.
7. Medir la alineación caja--JPEG y seleccionar/registrar el margen.
8. Ejecutar M0--M4 en las dos resoluciones y tres escenas del protocolo.
9. Resumir por `run_id + condición + resolución + escena`; no mezclar corridas.
10. Actualizar el manuscrito sólo con resultados físicos trazables a CSV,
    manifiesto y hash de fuentes.

## 10. Criterios mínimos para declarar el prototipo listo

- 100 % de recuperación exacta en los casos de prueba registrados para M3/M4;
- 100 % de rechazo en las mutaciones registradas;
- cero nonces repetidos bajo una misma clave;
- cero replays aceptados por el receptor de prueba;
- paquete persistido antes de presentar éxito en la WebUI;
- la WebUI experimental no incrusta ni enlaza el stream crudo;
- métricas físicas separadas de los diagnósticos del equipo de desarrollo;
- tasa de salida calculada con timestamps, no inferida de la cámara;
- limitación de cajas/cuadros y rostros no detectados declarada;
- metadatos de placa, cámara, software, escena y consentimiento completos.

## 11. Qué falta medir en la placa

El código y las pruebas de escritorio sólo pueden cerrar invariantes de
software. Para la versión de envío aún hacen falta FPS de salida protegida,
latencias p50/p95 por etapa, CPU/RAM, temperatura si es accesible, descartes
observables, tamaño de paquetes, precisión/recall/IoU del detector mediante una
fuente anotada y las pruebas físicas de recuperación, modificación y replay.
Hasta completar esa campaña, ninguna cifra de PC debe atribuirse al QRB2210 o
al STM32U585.
