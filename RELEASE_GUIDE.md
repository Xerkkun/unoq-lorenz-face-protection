# Guía del paquete de evidencia UNO Q v4

El script `prepare_unoq_release.ps1` audita una lista blanca y, sólo cuando se
solicita, construye un ZIP reproducible bajo `../release/`.

Desde PowerShell, en este directorio:

```powershell
# Auditoría sin modificar salidas
.\prepare_unoq_release.ps1

# Construcción después de una auditoría satisfactoria
.\prepare_unoq_release.ps1 -Build

# Reemplazo explícito de una salida ya revisada
.\prepare_unoq_release.ps1 -Build -Force
```

Si la política local bloquea scripts, use el alcance de este proceso sin
cambiar la política del equipo:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\prepare_unoq_release.ps1
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\prepare_unoq_release.ps1 -Build -Force
```

La auditoría valida que el JSON y el CSV sean evidencia del host de desarrollo,
que los 50 casos declarados coincidan y aprueben recuperación, rechazo de
alteraciones, rechazo de repetición y serialización. La plantilla de placa debe
seguir marcada como `template_not_a_completed_run` y sin `run_id`.

El paquete incluye código Python, adaptador App Lab, WebUI, sketch, pruebas,
scripts de verificación, avisos de terceros, protocolos, plantilla de manifiesto
de placa y los resultados permitidos del host. También genera dentro del ZIP:

- `PACKAGE_README.md`, con la frontera de evidencia;
- `MANIFEST.sha256`, con hash y tamaño de cada archivo salvo el propio
  manifiesto;
- rutas ordenadas y una fecha ZIP fija, comprobadas con dos construcciones en
  memoria antes de escribir el archivo.

Se excluyen por diseño claves y contratos privados, variables `.env`, datos
crudos, rostros, imágenes y video, participantes, consentimientos, resultados
físicos de placa, `raw/`, cachés, bytecode, entornos virtuales y artefactos de
compilación. El archivo `unoq_lorenz_software_v4.zip.sha256` permite verificar
el ZIP sin abrirlo:

```powershell
$releaseRoot = if (Test-Path .\docs) { ".\release" } else { "..\release" }
Get-FileHash "$releaseRoot\unoq_lorenz_software_v4.zip" -Algorithm SHA256
Get-Content "$releaseRoot\unoq_lorenz_software_v4.zip.sha256"
```

La presencia del ZIP no convierte los tiempos del host en mediciones de Arduino
UNO Q. El piloto físico del 28-07-2026 se conserva en un conjunto separado y no
se incluye en el ZIP; la campaña comparativa registrada sigue pendiente.
