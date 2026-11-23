$ErrorActionPreference = 'Continue'
$PY = 'C:\Python314\python.exe'
$ROOT = 'D:\STEAM入库\全自动入库_v2'
$DIR = "$ROOT\src"

$pargs = @(
  '-m', 'PyInstaller', '--noconfirm', '--clean', '--onefile', '--windowed',
  '--name', 'RukuCenter',
  '--add-data', "$DIR\depotkeys_master.json;.",
  '--add-data', "$DIR\crack_library.json;.",
  '--add-data', "$DIR\names.json;.",
  '--distpath', "$ROOT\dist",
  '--workpath', "$ROOT\build",
  '--specpath', "$ROOT",
  "$DIR\main_app.py"
)
& $PY @pargs *>&1

$exe = "$ROOT\dist\RukuCenter.exe"
if (-not (Test-Path -LiteralPath $exe)) { Write-Output 'BUILD FAILED: no exe'; exit 1 }
$dst = "$ROOT\入库中心.exe"
if (Test-Path -LiteralPath $dst) {
    $old = "$ROOT\入库中心_old_$(Get-Date -Format yyyyMMdd_HHmmss).exe"
    Move-Item -LiteralPath $dst -Destination $old -Force
}
Copy-Item -LiteralPath $exe -Destination $dst -Force
foreach ($f in @('depotkeys_master.json','crack_library.json','names.json')) {
    Copy-Item -LiteralPath "$DIR\$f" -Destination "$ROOT\$f" -Force
}
$h = (Get-FileHash -LiteralPath $dst -Algorithm SHA256).Hash
$s = (Get-Item -LiteralPath $dst).Length
Write-Output "OK exe=$dst size=$s sha256=$h"
