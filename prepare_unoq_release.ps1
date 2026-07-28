[CmdletBinding()]
param(
    [switch]$Build,
    [switch]$Force
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$SoftwareRoot = [System.IO.Path]::GetFullPath($PSScriptRoot)
$ProjectRoot = [System.IO.Path]::GetFullPath((Join-Path $SoftwareRoot ".."))
$ReleaseRoot = [System.IO.Path]::GetFullPath((Join-Path $ProjectRoot "release"))
$PackageName = "unoq_lorenz_software_v3"
$ZipPath = Join-Path $ReleaseRoot ($PackageName + ".zip")
$SidecarPath = $ZipPath + ".sha256"
$FixedZipTimestamp = [DateTimeOffset]::Parse("2026-07-28T00:00:00Z")

function Assert-PathInsideRoot {
    param(
        [Parameter(Mandatory = $true)][string]$Path,
        [Parameter(Mandatory = $true)][string]$Root
    )

    $fullPath = [System.IO.Path]::GetFullPath($Path)
    $fullRoot = [System.IO.Path]::GetFullPath($Root).TrimEnd(
        [System.IO.Path]::DirectorySeparatorChar,
        [System.IO.Path]::AltDirectorySeparatorChar
    )
    $prefix = $fullRoot + [System.IO.Path]::DirectorySeparatorChar
    if (($fullPath -ne $fullRoot) -and
        (-not $fullPath.StartsWith($prefix, [StringComparison]::OrdinalIgnoreCase))) {
        throw "Ruta fuera del alcance permitido: $fullPath (raiz: $fullRoot)"
    }
    return $fullPath
}

function Get-RelativePathPortable {
    param(
        [Parameter(Mandatory = $true)][string]$BasePath,
        [Parameter(Mandatory = $true)][string]$ChildPath
    )

    $baseFull = [System.IO.Path]::GetFullPath($BasePath).TrimEnd(
        [System.IO.Path]::DirectorySeparatorChar,
        [System.IO.Path]::AltDirectorySeparatorChar
    ) + [System.IO.Path]::DirectorySeparatorChar
    $childFull = [System.IO.Path]::GetFullPath($ChildPath)
    $baseUri = New-Object System.Uri($baseFull)
    $childUri = New-Object System.Uri($childFull)
    return [System.Uri]::UnescapeDataString(
        $baseUri.MakeRelativeUri($childUri).ToString()
    ).Replace("\", "/")
}

function Get-Sha256HexFromBytes {
    param([Parameter(Mandatory = $true)][byte[]]$Bytes)

    $sha = [System.Security.Cryptography.SHA256]::Create()
    try {
        $digest = $sha.ComputeHash($Bytes)
        return ([System.BitConverter]::ToString($digest)).Replace("-", "").ToLowerInvariant()
    }
    finally {
        $sha.Dispose()
    }
}

function Read-StrictUtf8 {
    param([Parameter(Mandatory = $true)][string]$Path)

    $decoder = New-Object System.Text.UTF8Encoding($false, $true)
    return $decoder.GetString([System.IO.File]::ReadAllBytes($Path))
}

function Add-PackageEntry {
    param(
        [Parameter(Mandatory = $true)][AllowEmptyCollection()][System.Collections.ArrayList]$Entries,
        [Parameter(Mandatory = $true)][string]$SourcePath,
        [Parameter(Mandatory = $true)][string]$ArchivePath
    )

    $sourceFull = Assert-PathInsideRoot -Path $SourcePath -Root $ProjectRoot
    if (-not [System.IO.File]::Exists($sourceFull)) {
        throw "Falta archivo requerido: $sourceFull"
    }
    $item = Get-Item -LiteralPath $sourceFull -Force
    if (($item.Attributes -band [System.IO.FileAttributes]::ReparsePoint) -ne 0) {
        throw "No se permiten enlaces ni puntos de reparacion: $sourceFull"
    }

    $portableArchivePath = $ArchivePath.Replace("\", "/").TrimStart("/")
    if ($portableArchivePath.Contains("../") -or $portableArchivePath.Contains(":") -or
        [string]::IsNullOrWhiteSpace($portableArchivePath)) {
        throw "Ruta interna invalida: $ArchivePath"
    }
    if ($Entries | Where-Object { $_.ArchivePath -eq $portableArchivePath }) {
        throw "Ruta interna duplicada: $portableArchivePath"
    }

    [void]$Entries.Add([pscustomobject]@{
        SourcePath = $sourceFull
        ArchivePath = $portableArchivePath
        Bytes = [System.IO.File]::ReadAllBytes($sourceFull)
    })
}

function Test-TextForSecrets {
    param(
        [Parameter(Mandatory = $true)][string]$ArchivePath,
        [Parameter(Mandatory = $true)][string]$Text
    )

    $secretPatterns = @(
        "-----BEGIN (?:RSA |EC |OPENSSH |DSA )?PRIVATE KEY-----",
        '(?im)^\s*(?:UNOQ_MASTER_KEY_B64|MASTER_KEY|API_KEY|ACCESS_TOKEN|PASSWORD)\s*[:=]\s*[''"]?[A-Za-z0-9+/=_-]{32,}[''"]?\s*$',
        "\bAKIA[0-9A-Z]{16}\b",
        "\bgh[pousr]_[A-Za-z0-9]{30,}\b",
        "\bxox[baprs]-[A-Za-z0-9-]{20,}\b"
    )
    foreach ($pattern in $secretPatterns) {
        if ([regex]::IsMatch($Text, $pattern)) {
            throw "Posible secreto detectado en $ArchivePath (patron: $pattern)"
        }
    }
}

function Get-AuditedEntries {
    $entries = New-Object System.Collections.ArrayList

    $softwareExact = @(
        "app.yaml",
        "pyproject.toml",
        "README.md",
        "THIRD_PARTY_NOTICES.md",
        "prepare_unoq_release.ps1",
        "RELEASE_GUIDE.md",
        "assets/app.js",
        "assets/index.html",
        "assets/style.css",
        "assets/libs/arduino.js",
        "assets/libs/qrcode.min.js",
        "assets/libs/socket.io.min.js",
        "sketch/README.md",
        "sketch/sketch.ino",
        "sketch/sketch.yaml",
        "data/software_verification_cases.csv",
        "data/software_verification_summary.json",
        "data/board/README.md",
        "data/board/run_manifest_template.json"
    )
    foreach ($relative in $softwareExact) {
        Add-PackageEntry -Entries $entries `
            -SourcePath (Join-Path $SoftwareRoot $relative) `
            -ArchivePath ($PackageName + "/" + $relative)
    }

    $sourceGroups = @(
        @{ Directory = "python"; Filter = "*.py"; Recurse = $true },
        @{ Directory = "scripts"; Filter = "*.py"; Recurse = $false },
        @{ Directory = "tests"; Filter = "test_*.py"; Recurse = $false }
    )
    foreach ($group in $sourceGroups) {
        $directory = Join-Path $SoftwareRoot $group.Directory
        if (-not [System.IO.Directory]::Exists($directory)) {
            throw "Falta directorio requerido: $directory"
        }
        $files = Get-ChildItem -LiteralPath $directory -File -Filter $group.Filter `
            -Recurse:$group.Recurse | Sort-Object FullName
        if ($files.Count -eq 0) {
            throw "No se encontraron archivos $($group.Filter) en $directory"
        }
        foreach ($file in $files) {
            $relative = Get-RelativePathPortable -BasePath $SoftwareRoot -ChildPath $file.FullName
            Add-PackageEntry -Entries $entries -SourcePath $file.FullName `
                -ArchivePath ($PackageName + "/" + $relative)
        }
    }

    $projectDocuments = @(
        "EXPERIMENT_PROTOCOL.md",
        "MANUAL_REPRODUCCION_ESTUDIANTES.md",
        "PROTOCOLO_Y_ETICA.md",
        "STUDENT_REPRODUCTION_MANUAL.md",
        "TEORIA_Y_DISENO_SOFTWARE.md"
    )
    foreach ($document in $projectDocuments) {
        Add-PackageEntry -Entries $entries `
            -SourcePath (Join-Path $ProjectRoot $document) `
            -ArchivePath ($PackageName + "/docs/" + $document)
    }

    $allowedExtensions = @(
        ".csv", ".css", ".html", ".ino", ".js", ".json", ".md",
        ".ps1", ".py", ".toml", ".yaml", ".yml"
    )
    foreach ($entry in $entries) {
        $extension = [System.IO.Path]::GetExtension($entry.ArchivePath).ToLowerInvariant()
        if ($allowedExtensions -notcontains $extension) {
            throw "Tipo de archivo no permitido: $($entry.ArchivePath)"
        }
        if ($entry.ArchivePath -match "(?i)(^|/)(raw|private|secrets?|keys?|faces?|rostros?|participants?)(/|$)" -or
            $entry.ArchivePath -match "(?i)(__pycache__|\.pytest_cache|\.venv|venv|\.pyc$|\.pyo$|\.pem$|\.key$|\.env$)") {
            throw "Ruta prohibida en el paquete: $($entry.ArchivePath)"
        }
        $text = Read-StrictUtf8 -Path $entry.SourcePath
        Test-TextForSecrets -ArchivePath $entry.ArchivePath -Text $text
    }

    $summaryPath = Join-Path $SoftwareRoot "data/software_verification_summary.json"
    $summary = Get-Content -LiteralPath $summaryPath -Raw -Encoding UTF8 | ConvertFrom-Json
    if ($summary.status -ne "passed_software_verification_on_development_host" -or
        $summary.all_required_checks_passed -ne $true -or
        $summary.not_uno_q_measurements -ne $true) {
        throw "La evidencia JSON no conserva la frontera host/UNO Q requerida."
    }
    if ([int]$summary.cases -le 0) {
        throw "El resumen de verificacion no contiene casos ejecutados."
    }

    $casePath = Join-Path $SoftwareRoot "data/software_verification_cases.csv"
    $cases = @(Import-Csv -LiteralPath $casePath -Encoding UTF8)
    if ($cases.Count -ne [int]$summary.cases) {
        throw "El CSV contiene $($cases.Count) casos; el resumen declara $($summary.cases)."
    }
    foreach ($field in @("exact_recovery", "tamper_rejected", "replay_rejected", "serialization_round_trip")) {
        if (@($cases | Where-Object { $_.$field -ne "1" }).Count -ne 0) {
            throw "Hay casos sin aprobar en la columna $field."
        }
    }

    $boardTemplatePath = Join-Path $SoftwareRoot "data/board/run_manifest_template.json"
    $boardTemplate = Get-Content -LiteralPath $boardTemplatePath -Raw -Encoding UTF8 | ConvertFrom-Json
    if ($boardTemplate.status -ne "template_not_a_completed_run" -or $null -ne $boardTemplate.run_id) {
        throw "El manifiesto de placa parece contener una corrida real; no se empaquetara."
    }

    $archivePaths = @($entries | ForEach-Object { $_.ArchivePath })
    if ($archivePaths | Where-Object {
        $_ -match "(?i)data/board/raw/" -or
        $_ -match "(?i)data/board/(?!run_manifest_template\.json$).*\.(csv|json)$"
    }) {
        throw "Se intento incluir una medicion fisica de placa no autorizada."
    }

    return @($entries | Sort-Object ArchivePath)
}

function Get-PackageReadmeBytes {
    $text = @'
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
'@
    $encoding = New-Object System.Text.UTF8Encoding($false)
    return $encoding.GetBytes($text.Replace("`r`n", "`n").TrimEnd() + "`n")
}

function Get-ManifestBytes {
    param([Parameter(Mandatory = $true)][object[]]$Entries)

    $lines = New-Object System.Collections.Generic.List[string]
    $lines.Add("# SHA-256 manifest; MANIFEST.sha256 is intentionally excluded from itself.")
    foreach ($entry in $Entries | Sort-Object ArchivePath) {
        $hash = Get-Sha256HexFromBytes -Bytes $entry.Bytes
        $lines.Add(("{0}  {1,12}  {2}" -f $hash, $entry.Bytes.Length, $entry.ArchivePath))
    }
    $encoding = New-Object System.Text.UTF8Encoding($false)
    return $encoding.GetBytes(($lines -join "`n") + "`n")
}

function New-DeterministicZipBytes {
    param([Parameter(Mandatory = $true)][object[]]$Entries)

    Add-Type -AssemblyName System.IO.Compression
    $memory = New-Object System.IO.MemoryStream
    $archive = New-Object System.IO.Compression.ZipArchive(
        $memory,
        [System.IO.Compression.ZipArchiveMode]::Create,
        $true
    )
    try {
        foreach ($item in $Entries | Sort-Object ArchivePath) {
            $zipEntry = $archive.CreateEntry(
                $item.ArchivePath,
                [System.IO.Compression.CompressionLevel]::Optimal
            )
            $zipEntry.LastWriteTime = $FixedZipTimestamp
            $stream = $zipEntry.Open()
            try {
                $stream.Write($item.Bytes, 0, $item.Bytes.Length)
            }
            finally {
                $stream.Dispose()
            }
        }
    }
    finally {
        $archive.Dispose()
    }
    try {
        return $memory.ToArray()
    }
    finally {
        $memory.Dispose()
    }
}

$entries = @(Get-AuditedEntries)
$totalBytes = ($entries | ForEach-Object { $_.Bytes.Length } | Measure-Object -Sum).Sum
Write-Host ("AUDIT OK: {0} archivos permitidos, {1} bytes; evidencia fisica incluida: 0." -f `
    $entries.Count, $totalBytes)
Write-Host "Frontera verificada: resultados de host + plantilla vacia de placa."

if (-not $Build) {
    Write-Host "No se construyo ningun ZIP. Use -Build despues de revisar esta auditoria."
    exit 0
}

$packageReadme = [pscustomobject]@{
    SourcePath = $null
    ArchivePath = $PackageName + "/PACKAGE_README.md"
    Bytes = Get-PackageReadmeBytes
}
$entriesWithReadme = @($entries) + @($packageReadme)
$manifest = [pscustomobject]@{
    SourcePath = $null
    ArchivePath = $PackageName + "/MANIFEST.sha256"
    Bytes = Get-ManifestBytes -Entries $entriesWithReadme
}
$finalEntries = @($entriesWithReadme) + @($manifest)

[void](Assert-PathInsideRoot -Path $ReleaseRoot -Root $ProjectRoot)
[void](Assert-PathInsideRoot -Path $ZipPath -Root $ReleaseRoot)
[void](Assert-PathInsideRoot -Path $SidecarPath -Root $ReleaseRoot)

if (([System.IO.File]::Exists($ZipPath) -or [System.IO.File]::Exists($SidecarPath)) -and -not $Force) {
    throw "La salida ya existe. Revise el paquete y use -Build -Force para reemplazarlo de forma explicita."
}
if (-not [System.IO.Directory]::Exists($ReleaseRoot)) {
    [void][System.IO.Directory]::CreateDirectory($ReleaseRoot)
}

$zipBytes = New-DeterministicZipBytes -Entries $finalEntries
$secondBuildBytes = New-DeterministicZipBytes -Entries $finalEntries
$zipHash = Get-Sha256HexFromBytes -Bytes $zipBytes
$secondHash = Get-Sha256HexFromBytes -Bytes $secondBuildBytes
if ($zipHash -ne $secondHash -or $zipBytes.Length -ne $secondBuildBytes.Length) {
    throw "La comprobacion interna de reproducibilidad del ZIP fallo."
}

if ($Force) {
    if ([System.IO.File]::Exists($ZipPath)) {
        [System.IO.File]::Delete($ZipPath)
    }
    if ([System.IO.File]::Exists($SidecarPath)) {
        [System.IO.File]::Delete($SidecarPath)
    }
}

[System.IO.File]::WriteAllBytes($ZipPath, $zipBytes)
$encoding = New-Object System.Text.UTF8Encoding($false)
[System.IO.File]::WriteAllText(
    $SidecarPath,
    ($zipHash + "  " + [System.IO.Path]::GetFileName($ZipPath) + "`n"),
    $encoding
)

$writtenHash = (Get-FileHash -LiteralPath $ZipPath -Algorithm SHA256).Hash.ToLowerInvariant()
if ($writtenHash -ne $zipHash) {
    throw "El ZIP escrito no coincide con el digest calculado."
}

Write-Host "BUILD OK: $ZipPath"
Write-Host "SHA256: $zipHash"
Write-Host "Sidecar: $SidecarPath"
