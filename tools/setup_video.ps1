#Requires -Version 5.1
<#
.SYNOPSIS
  Install the Shoestring Studios video toolchain on Windows.
.DESCRIPTION
  Checks Node.js, ffmpeg and espeak-ng, installs the Remotion
  cut-slide renderer (video/remotion/node_modules via npm), and
  prints a status table. Idempotent: steps already done are
  skipped. Never renders video, never calls a model.
.EXAMPLE
  powershell -ExecutionPolicy Bypass -File tools/setup_video.ps1
#>
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$remotion = Join-Path $root "video/remotion"
$rows = @()

function Add-Row($name, $ok, $detail) {
  $script:rows += [pscustomobject]@{ Tool = $name; OK = $ok;
                                     Detail = $detail }
}

# 1. Node.js >= 16 (needed for Remotion)
try {
  $nv = (node --version 2>$null)
  $major = [int](($nv -replace '^v', '') -split '\.')[0]
  if ($major -ge 16) { Add-Row "node" "yes" "$nv" }
  else { Add-Row "node" "NO" "$nv (need >= 16)" }
} catch { Add-Row "node" "NO" "not on PATH (install from nodejs.org)" }

# 2. npm
try {
  $npmv = (npm --version 2>$null)
  Add-Row "npm" "yes" "$npmv"
} catch { Add-Row "npm" "NO" "not on PATH (ships with Node.js)" }

# 3. Remotion project deps
if ((Get-ChildItem Env:PATH).Value -and (Get-Command npm -ErrorAction SilentlyContinue)) {
  if (Test-Path (Join-Path $remotion "node_modules")) {
    Add-Row "remotion deps" "yes" "node_modules present"
  } else {
    Write-Output "Installing Remotion deps (npm install)..."
    Push-Location $remotion
    try { npm install --no-audit --no-fund 2>&1 | Select-Object -Last 3 }
    finally { Pop-Location }
    if (Test-Path (Join-Path $remotion "node_modules")) {
      Add-Row "remotion deps" "yes" "installed"
    } else {
      Add-Row "remotion deps" "NO" "npm install failed"
    }
  }
} else {
  Add-Row "remotion deps" "NO" "needs npm first"
}

# 4. ffmpeg (assembly fallback)
try {
  $fv = ((ffmpeg -version 2>$null) | Select-Object -First 1)
  if ($fv) { Add-Row "ffmpeg" "yes" "$fv" }
  else { Add-Row "ffmpeg" "NO" "not on PATH (install from ffmpeg.org)" }
} catch { Add-Row "ffmpeg" "NO" "not on PATH (install from ffmpeg.org)" }

# 5. espeak-ng (Kokoro English fallback)
try {
  $ev = ((espeak-ng --version 2>$null) | Select-Object -First 1)
  if ($ev) { Add-Row "espeak-ng" "yes" "$ev" }
  else { Add-Row "espeak-ng" "NO" "manual install (see PLAN §1b)" }
} catch { Add-Row "espeak-ng" "NO" "manual install (see PLAN §1b)" }

# 6. Kokoro TTS (pip package, needs torch)
try {
  $kv = (python -c "import importlib.metadata; print(importlib.metadata.version('kokoro'))" 2>$null)
  if ($kv) { Add-Row "kokoro" "yes" "$kv" }
  else { Add-Row "kokoro" "NO" "pip install -r requirements-video.txt" }
} catch { Add-Row "kokoro" "NO" "pip install -r requirements-video.txt" }

# 7. imageio-ffmpeg (pip-provided ffmpeg binary for assembly/smoke)
try {
  $iv = (python -c "import importlib.metadata; print(importlib.metadata.version('imageio-ffmpeg'))" 2>$null)
  if ($iv) { Add-Row "imageio-ffmpeg" "yes" "$iv" }
  else { Add-Row "imageio-ffmpeg" "NO" "pip install -r requirements-video.txt" }
} catch { Add-Row "imageio-ffmpeg" "NO" "pip install -r requirements-video.txt" }

$rows | Format-Table -AutoSize | Out-String | Write-Output
$missing = @($rows | Where-Object { $_.OK -eq "NO" })
if ($missing.Count -eq 0) {
  Write-Output "Video toolchain ready."
} else {
  Write-Output ("Remaining (" + $missing.Count + "): " +
    (($missing | ForEach-Object { $_.Tool }) -join ", "))
  Write-Output "Without them the app still runs; renders and local TTS record honest unavailable notes."
}
