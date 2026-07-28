# Manual de reproducción para estudiantes de ingeniería

## 1. Propósito y alcance

Este manual acompaña el artículo sobre protección autenticada de regiones
faciales en Arduino UNO Q. Su propósito es que un equipo de estudiantes pueda:

1. ejecutar la verificación sin cámara mediante imágenes sintéticas;
2. comprender cómo se construyen la permutación, la máscara y el paquete
   autenticado;
3. desplegar la aplicación en una UNO Q y usar un celular como cámara;
4. elegir conscientemente qué datos conservar, enviar o descartar;
5. medir el costo del procesamiento sin confundir resultados del host con
   resultados de la placa; y
6. documentar limitaciones de privacidad, detección y seguridad.

El prototipo es una plataforma educativa y de experimentación. No es un
producto biométrico certificado. La transformación derivada de Lorenz no se
presenta como cifrador. La confidencialidad e integridad de los paquetes M3 y
M4 provienen de ChaCha20-Poly1305, con separación de claves mediante
HKDF-SHA-256.

## 2. Resultados de aprendizaje

Al terminar la práctica, el estudiante podrá explicar:

- la diferencia entre ocultamiento visual, cifrado, autenticación y detección;
- por qué un rostro omitido por el detector no puede protegerse después;
- por qué un nonce no debe repetirse con la misma clave;
- qué información se autentica como datos asociados;
- cómo se recupera exactamente una ROI desde un paquete M3/M4;
- qué demuestra una prueba estadística de bits y qué no demuestra;
- por qué se separan el QRB2210 Linux y el STM32U585;
- cómo seleccionar una política de retención para una aplicación en tiempo real.

## 3. Frontera de afirmaciones

Mantenga separadas estas evidencias:

| Evidencia | Qué permite afirmar | Qué no permite afirmar |
|---|---|---|
| Pruebas unitarias en PC | Invariantes del código en ese entorno | Rendimiento de UNO Q |
| Casos sintéticos | Recuperación, rechazo de alteración y serialización | Exactitud con rostros reales |
| Piloto M4 en UNO Q | Integración celular--placa y tiempos preliminares | Comparación entre M0--M4 |
| Auditoría en memoria | Igualdad byte a byte de la ROI actual | Seguridad frente a todos los ataques |
| Pruebas NIST/TestU01/etc. | Defectos estadísticos observables | Seguridad criptográfica |
| Fotograma protegido | Frontera de visualización implementada | Recall del detector o secreto de clave |

No reetiquete tiempos de Windows como tiempos de QRB2210 o STM32U585. No
presente una imagen con apariencia ruidosa como prueba de confidencialidad.

## 4. Plataforma de referencia

### 4.1 Especificaciones del fabricante

Arduino UNO Q integra:

- procesador de aplicaciones Qualcomm Dragonwing QRB2210, cuatro núcleos Arm
  Cortex-A53 de hasta 2.0 GHz;
- GPU Adreno y dos procesadores de señal de imagen;
- microcontrolador STM32U585 Arm Cortex-M33 de hasta 160 MHz, 2 MB de flash y
  786 kB de SRAM;
- Debian Linux en el QRB2210 y sketches sobre Zephyr en el STM32U585;
- Wi-Fi 5 de 2.4/5 GHz, Bluetooth 5.1 y comunicación Bridge/RPC;
- variantes oficiales de 2 o 4 GB LPDDR4X y 16 o 32 GB eMMC.

### 4.2 Configuración observada en el piloto

Estos valores pertenecen a la placa y a la corrida del 28-07-2026; una
instalación posterior puede ser distinta:

| Elemento | Valor observado |
|---|---|
| Modelo reportado | Arduino UnoQ |
| RAM | variante de 4 GB; 3,755,164 kB utilizables reportados |
| Arquitectura | `aarch64`, cuatro CPU Kryo-V2, máximo 2016 MHz |
| Sistema | Debian GNU/Linux 13.5 (trixie) |
| Kernel | `7.0.0-g122c2c22d838` |
| App CLI/daemon | 0.12.1 / 0.12.1 |
| `arduino_app_bricks` | 0.11.0 |
| Python de la aplicación | 3.13.14 |
| NumPy | 2.4.6 |
| Cryptography | 49.0.0 |
| OpenCV | 4.13.0 |
| Entrada real | celular, JPEG decodificado de 480x640 vertical |
| Red observada | celular 2.4 GHz, UNO Q 5 GHz, LAN puenteada |

Registre de nuevo estas versiones en cada campaña. El perfil autenticado
incluye la versión de NumPy porque un cambio de API puede modificar la
permutación reproducida.

## 5. Material necesario

### Ruta sin cámara física

- computadora con Python 3.11 o posterior;
- Git;
- aproximadamente 1 GB libre;
- repositorio del proyecto.

### Ruta con placa

- Arduino UNO Q y fuente USB-C adecuada;
- computadora con Arduino App Lab;
- celular Android o iOS con Arduino IoT Remote;
- red local que permita comunicación entre clientes;
- consentimiento explícito de cualquier participante;
- opcional: instrumento identificado para potencia y temperatura.

El celular puede usar 2.4 GHz y la placa 5 GHz si el enrutador puentea ambas
bandas. Desactive “aislamiento de clientes”, red de invitados o reglas que
impidan el tráfico local.

## 6. Mapa del repositorio

```text
app.yaml                         definición de la aplicación App Lab
python/main.py                   adaptador de cámara, detector y WebUI
python/unoq_lorenz/              núcleo independiente de la plataforma
sketch/                          sketch para el STM32U585
assets/                          interfaz local y recursos de Arduino
tests/                           pruebas unitarias
scripts/run_verification.py      campaña sintética reproducible
scripts/generate_figures.py      figuras sin datos biométricos
scripts/summarize_board_metrics.py resumen de CSV de la placa
scripts/export_schedule_bitstreams.py flujos para pruebas estadísticas
data/                            evidencia pública no sensible
docs/                            teoría, protocolo, ética y este manual
```

Los paquetes de una corrida real, claves, video crudo, consentimientos e
imágenes de participantes no forman parte del repositorio público.

## 7. Preparación del entorno de la computadora

### 7.1 Windows PowerShell

```powershell
git clone https://github.com/Xerkkun/unoq-lorenz-face-protection.git
Set-Location unoq-lorenz-face-protection
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
python -m pytest -q
python scripts/run_verification.py
```

Si PowerShell impide activar el entorno, puede invocar directamente:

```powershell
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe scripts\run_verification.py
```

### 7.2 Linux o macOS

```bash
git clone https://github.com/Xerkkun/unoq-lorenz-face-protection.git
cd unoq-lorenz-face-protection
python3 -m venv .venv
. .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
python -m pytest -q
python scripts/run_verification.py
```

Una ejecución correcta termina sin fallas y produce evidencia sintética en
`data/`. Las mediciones obtenidas en esta sección son del host.

## 8. Cadena exacta para construir los bits

La cadena versionada es:

```text
K -> (K_A, K_L) -> estado Lorenz -> D_L
  -> HKDF(nonce, longitud, versión, D_L)
  -> semilla PCG64 -> permutación + máscara
  -> transformación reversible -> ChaCha20-Poly1305
```

### 8.1 Separación de claves

Cada corrida crea una clave maestra aleatoria `K` de 32 bytes. HKDF-SHA-256
deriva dos dominios independientes:

- `K_A`: clave de ChaCha20-Poly1305;
- `K_L`: clave del calendario numérico.

Nunca escriba `K` en el repositorio, `app.yaml`, URL, WebUI, CSV o manifiesto.
El manifiesto sólo puede incluir una huella SHA-256 no reversible.

### 8.2 Perfil numérico de Lorenz

El perfil `lorenz-rk4-sha256-pcg64-v2` usa:

- `sigma=10`, `rho=28`, `beta=8/3`;
- aritmética binary64;
- RK4 con paso fijo `h=0.005`;
- 2048 estados descartados;
- 512 estados conservados;
- multiplicación de cada coordenada por `10^9`;
- redondeo y serialización `int64` little-endian;
- SHA-256 para obtener `D_L`.

El cálculo ocurre una vez al construir el protector, no una vez por byte.

### 8.3 Calendario por paquete

Para cada nonce de 96 bits `N` y longitud de ROI `n`, HKDF-SHA-256 produce 32
bytes usando como información la versión, `n` y `D_L`. Los primeros 128 bits
inicializan `Generator(PCG64)`. La API genera primero una permutación y después
una máscara `uint8`.

PCG64 se usa por reproducibilidad del experimento. No se le atribuye
impredecibilidad criptográfica. La seguridad del paquete se apoya en
ChaCha20-Poly1305.

### 8.4 Transformación y recuperación

Si `P` contiene los bytes contiguos de la ROI:

```text
q[i] = p[permutation[i]] XOR mask[i]
p[permutation[i]] = q[i] XOR mask[i]
```

M4 cifra y autentica `Q`; M3 cifra y autentica `P` sin la etapa de Lorenz. El
receptor autentica primero, verifica el perfil y sólo después reconstruye la
ROI. Nunca entregue píxeles antes de verificar la etiqueta.

### 8.5 Nonce, metadatos y repetición

El nonce es un prefijo aleatorio de 64 bits concatenado con un contador de 32
bits asignado bajo exclusión mutua. Al agotarse el contador, el proceso falla
de forma cerrada. Los datos asociados autentican:

- identificadores de corrida, paquete, callback y ROI;
- caja, forma y tipo del arreglo;
- modo M3/M4;
- protocolo, AEAD, KDF y perfil completo;
- resumen SHA-256 del perfil.

El receptor registra un identificador o nonce como visto únicamente después de
autenticar. De esta manera, un paquete inválido no puede contaminar el estado
de repetición.

## 9. Exportación y evaluación estadística de bits

El script incluido genera flujos públicos deterministas de máscara para
enseñanza. No usa una clave de producción:

```powershell
python scripts/export_schedule_bitstreams.py `
  --output-dir data/bitstreams `
  --streams 10 `
  --bytes-per-stream 1000000
```

Revise `data/bitstreams/manifest.json`. Cada archivo debe tener longitud y
SHA-256 registrados. Use varios flujos independientes y fije antes:

- cantidad de secuencias;
- bytes por secuencia;
- nivel de significancia;
- reglas para múltiples comparaciones;
- criterio de aprobación y de repetición.

Posibles suites: NIST SP 800-22, TestU01, PractRand y Dieharder. Convierta el
formato sólo mediante herramientas que preserven exactamente el orden de bits
y documente endianidad. Un resultado favorable no demuestra secreto de clave,
impredecibilidad, resistencia a texto elegido ni seguridad de nonce.

Perfiles futuros podrían emplear SHA-3 o BLAKE para extracción, ChaCha20 o
AES-CTR DRBG como generador seguro, fuentes de entropía independientes o mapas
no lineales acoplados. Cada cambio exige un identificador de perfil nuevo y
pruebas de compatibilidad, funcionalidad y seguridad.

## 10. Despliegue en Arduino UNO Q

1. Abra Arduino App Lab.
2. Duplique el ejemplo oficial **Detect Objects on Smartphone Camera**.
3. Sustituya `app.yaml` y `python/main.py`.
4. Copie `python/unoq_lorenz/`, `assets/` y `sketch/`.
5. Verifique que el modelo sea `face-detection`.
6. Mantenga el celular y la placa en la misma LAN confiable.
7. Inicie la aplicación.
8. Abra Arduino IoT Remote en el celular y escanee el código de seis dígitos.
9. Espere a que la WebUI muestre callbacks positivos.

El código de seis dígitos empareja el transporte de cámara; no es la clave
maestra del paquete ROI. La capa de transporte y el AEAD del artículo son
fronteras diferentes.

## 11. Contrato de corrida

La opción más reproducible es crear, fuera del repositorio, el archivo
`/app/data/private/run_config.json`:

```json
{
  "run_id": "20260728_student01",
  "scene": "stationary",
  "condition": "M4_lorenz_aead",
  "bbox_margin_fraction": 0.10,
  "inline_integrity_audit": false,
  "publication_frame_enabled": false
}
```

También pueden usarse variables:

```text
UNOQ_RUN_ID=20260728_student01
UNOQ_SCENE=stationary
UNOQ_CONDITION=M4_lorenz_aead
UNOQ_BBOX_MARGIN_FRACTION=0.10
```

Las variables tienen prioridad. Use un identificador nuevo y una clave nueva
después de cada reinicio.

### Condiciones

| ID | Operación | Uso |
|---|---|---|
| M0 | detección sin modificar ROI | línea base insegura |
| M1 | desenfoque gaussiano | ocultamiento visual, sin autenticación |
| M2 | sólo transformación Lorenz | ablación reversible no autenticada |
| M3 | AEAD de ROI original | línea criptográfica estándar |
| M4 | Lorenz + AEAD | composición propuesta |

M0--M2 están bloqueadas salvo que se defina
`UNOQ_ALLOW_INSECURE_ABLATION=1`. Úselas sólo en una red aislada y para el
experimento registrado.

## 12. Manejo de datos en tiempo real

Antes de iniciar una corrida, seleccione una política y escríbala en el
protocolo. No mezcle políticas dentro de una misma comparación.

### 12.1 Política A: procesamiento efímero

Flujo:

```text
celular -> detección -> M3/M4 -> vista protegida -> descarte
```

Conserve sólo métricas agregadas sin identificadores personales. Use buffers
acotados y sobrescriba referencias a arreglos al terminar el callback. Esta
política minimiza datos, pero no ofrece historial recuperable.

Adecuada para prácticas y demostraciones. No es apropiada si se exige auditoría
posterior o reconstrucción autorizada.

### 12.2 Política B: computadora local

Flujo:

```text
UNO Q -> paquete autenticado -> TLS/LAN -> receptor de laboratorio -> disco
```

Requisitos:

- autenticar el receptor, no sólo su dirección IP;
- aceptar únicamente M3/M4;
- escribir primero a un archivo temporal y publicar de forma atómica;
- confirmar recepción antes de eliminar la copia de la placa;
- usar el `packet_id` y el hash para hacer reintentos idempotentes;
- restringir firewall y permisos;
- almacenar la clave en un área distinta de los paquetes;
- definir una fecha de eliminación.

Si se pierde la red, elija por adelantado entre búfer acotado, contrapresión o
descarte explícito. Un búfer ilimitado puede llenar la eMMC y detener la
aplicación.

### 12.3 Política C: servicio remoto o nube

Flujo:

```text
UNO Q -> TLS mutuo/VPN -> cola u objetos -> procesamiento autorizado
```

Use credenciales de mínimo privilegio, rotación, auditoría del servidor,
cifrado en reposo y reglas automáticas de ciclo de vida. Evite incluir la clave
de recuperación en el mismo objeto o cuenta que contiene los paquetes. Registre
región de almacenamiento, responsables, finalidad, plazo y procedimiento de
borrado.

El cifrado de transporte no sustituye al paquete AEAD; protege otra frontera.
La nube puede observar tiempos, tamaños y frecuencia aunque no descifre la ROI.
Si esa fuga importa, agregue relleno y tráfico de cobertura bajo un protocolo
separado y medido.

### 12.4 Política D: fotogramas por eventos

Flujo:

```text
buffer circular en RAM -> evento -> ventana previa/posterior -> paquetes M3/M4
```

Defina el evento de manera verificable: botón del operador, entrada digital,
cruce de una zona, cambio de estado u otra señal. Documente:

- segundos previos y posteriores;
- si el búfer guarda sólo paquetes protegidos;
- prioridad cuando ocurren eventos simultáneos;
- cuota máxima por hora o día;
- deduplicación;
- falsos positivos y falsos negativos del disparador;
- quién puede recuperar el contenido;
- plazo de borrado.

No use un JPEG operacional como artefacto recuperable. Si se necesita
recuperación exacta, conserve el paquete autenticado. Para una figura de
publicación, active `publication_frame_enabled` y un archivo privado de armado;
se guarda una sola vista ya protegida, nunca el fotograma fuente.

### 12.5 Metadatos mínimos

Conserve sólo lo necesario:

- `run_id`, `packet_id` y tiempo monotónico o tiempo de evento;
- condición y versión del protocolo;
- forma de la ROI y, sólo si es necesario, caja delimitadora;
- nonce, ciphertext, etiqueta y datos asociados;
- huellas de software y perfil;
- estado de entrega/retención.

Evite nombres, número de teléfono, SSID, dirección privada, serie de placa,
ubicación o identificadores de cuenta en el repositorio público.

## 13. Auditoría de integridad y captura armada

Para una corrida dedicada de integridad:

```json
{
  "inline_integrity_audit": true,
  "publication_frame_enabled": false
}
```

Cada ROI se recupera y compara byte a byte en memoria. También se altera una
copia del ciphertext y se exige rechazo. No combine estos tiempos con una
corrida de rendimiento.

Para dar tiempo al operador a acomodar el celular:

```json
{
  "inline_integrity_audit": true,
  "publication_frame_enabled": true,
  "publication_frame_arm_file": "/app/data/private/capture.ready"
}
```

La aplicación sigue transmitiendo, pero no guarda la figura hasta que exista
`capture.ready`. Cree el archivo sólo después de recibir la señal del
participante. La aplicación lo elimina al guardar una vista protegida.

## 14. Campaña física recomendada

Para una comparación completa:

1. realice calentamiento;
2. pruebe M0--M4;
3. use 640x480 y 1280x720 si la fuente realmente las entrega;
4. incluya rostro estacionario, movimiento y cambio controlado de iluminación;
5. ejecute cinco corridas de 60 s por celda;
6. use clave, proceso y `run_id` nuevos por corrida;
7. no mezcle la auditoría en memoria con mediciones de rendimiento;
8. anote al menos 300 fotogramas distribuidos para presencia y solapamiento;
9. registre potencia/temperatura sólo con sensor identificado;
10. conserve filas crudas y resúmenes agrupados.

El callback oficial inspeccionado sólo informa detecciones positivas y la caja
no comparte un ID de fuente con el JPEG. Por ello, recall, fotogramas perdidos
y alineación requieren una fuente sincronizada o instrumentación adicional.

## 15. Métricas y unidades

No mezcle:

- `roi_spatial_pixels`: alto por ancho;
- `roi_bytes`: bytes contiguos de la ROI;
- `preview_jpeg_bytes`: tamaño del JPEG con pérdida;
- `packet_bytes`: paquete serializado;
- `packet_count`: número de ROI aceptadas.

Reporte mediana y percentil 95 de decodificación, protección, escritura
atómica, codificación de vista y callback. Reporte por separado salidas
operacionales por segundo, paquetes autenticados por segundo y bytes por
segundo. La diferencia M3--M4 estima el costo incremental de la etapa Lorenz.

Resuma los CSV físicos con:

```powershell
python scripts/summarize_board_metrics.py data/board/raw/*.csv
```

No pase a ese comando el CSV de verificación sintética.

## 16. Solución de problemas

### La placa aparece fuera de línea

- confirme alimentación y estado en App Lab;
- cierre una instancia anterior que conserve el puerto;
- reinicie sólo la aplicación antes de reiniciar toda la placa;
- verifique que computadora, placa y celular conserven conectividad local;
- genere un código de emparejamiento nuevo después de reconectar.

### El celular tiene Internet pero no conecta

Internet no garantiza LAN local. Desactive datos móviles durante la prueba,
red de invitados, aislamiento AP, VPN y cambio automático de red. Confirme que
2.4 y 5 GHz estén puenteadas.

### No aparecen rostros

- compruebe modelo `face-detection` y confianza 0.50;
- use iluminación frontal y rostro completo;
- no concluya que no hubo fotogramas: el callback puede omitir negativos;
- revise orientación y margen de caja.

### Hay vista, pero no paquetes

M0--M2 no producen protección autenticada. Use M3/M4. Revise espacio,
permisos, directorio privado y mensajes `pipeline_error`. El sistema elimina
una vista obsoleta si falla el almacenamiento.

### No se puede recuperar

Verifique clave, nonce, datos asociados, perfil, versión de NumPy y estado de
repetición. No intente recuperar desde el JPEG: es una vista con pérdida.

### La eMMC se llena

Detenga la corrida, preserve el manifiesto y aplique la política de retención.
No elimine directorios amplios mediante patrones sin verificar la ruta exacta.
Para producción, use cuotas, rotación y alarmas antes de alcanzar el límite.

## 17. Privacidad, ética y seguridad

- Comience con datos sintéticos.
- Use sólo adultos con consentimiento explícito cuando sea necesario.
- Explique finalidad, datos retenidos, responsables y fecha de eliminación.
- No publique claves, video crudo, ROI originales ni consentimientos.
- Un rostro omitido queda visible: mida y declare esta limitación.
- M0--M2 son modos inseguros.
- No exponga la WebUI mediante túneles o reenvío público de puertos.
- Una muestra pequeña no permite conclusiones de equidad.
- Consulte revisión institucional y legislación aplicable antes de estudiar
  personas o desplegar vigilancia.

## 18. Lista de verificación reproducible

Antes de la corrida:

- [ ] repositorio y commit registrados;
- [ ] pruebas unitarias aprobadas;
- [ ] versiones de placa y software registradas;
- [ ] condición, escena, resolución y duración fijadas;
- [ ] política de datos y plazo de retención elegidos;
- [ ] `run_id` y clave nuevos;
- [ ] red aislada y sin túnel público;
- [ ] consentimiento y autorización institucional resueltos;
- [ ] espacio de almacenamiento suficiente.

Después de la corrida:

- [ ] CSV y manifiesto cerrados;
- [ ] huellas SHA-256 calculadas;
- [ ] nonces e identificadores sin repetición;
- [ ] auditoría de autenticación documentada;
- [ ] fuente cruda no conservada;
- [ ] paquetes privados fuera del repositorio;
- [ ] resultados clasificados como host, piloto o campaña;
- [ ] eliminación programada y responsable asignado.

## 19. Actividades sugeridas

1. Cambie un byte del ciphertext, etiqueta, nonce y datos asociados por
   separado; documente el rechazo.
2. Ejecute M3 y M4 sobre las mismas dimensiones sintéticas y compare costo sin
   atribuir seguridad a Lorenz.
3. Genere diez flujos de bits y diseñe un plan estadístico previo.
4. Implemente un receptor local con escritura atómica e idempotencia.
5. Diseñe una política por eventos con búfer acotado y calcule el peor caso de
   almacenamiento.
6. Modele la fuga de tamaños y frecuencia de paquetes.
7. Instrumente una fuente con ID compartido para estudiar alineación.
8. Proponga un perfil con generador criptográficamente seguro y defina cómo
   versionarlo sin romper paquetes existentes.

La entrega de cada actividad debe incluir código, versiones, datos crudos no
sensibles, criterios de éxito y una sección breve titulada “Qué no demuestra
este resultado”.
