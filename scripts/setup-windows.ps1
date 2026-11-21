[CmdletBinding()]
param([switch]$Check, [switch]$SmokeTest, [string]$StartConfig)
$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath (Join-Path $PSScriptRoot '..')
$venv = Join-Path (Get-Location) '.venv\Scripts\python.exe'
# Check the interpreter itself: PATH and launcher names do not identify the architecture.
$probe = "import sys,sysconfig; print(sys.executable); sys.exit(0 if sys.implementation.name=='cpython' and sys.version_info[:2] in ((3,11),(3,12)) and sysconfig.get_platform()=='win-amd64' else 1)"

function Find-Python {
    # A missing launcher version can legitimately report an error on stderr.
    $ErrorActionPreference = "Continue"
    foreach ($version in @('3.12','3.11')) {
        $tag = $version.Replace('.','')
        $candidates = @()
        foreach ($key in @("HKCU:\Software\Python\PythonCore\$version\InstallPath",
                           "HKLM:\Software\Python\PythonCore\$version\InstallPath")) {
            if (Test-Path $key) {
                $directory = (Get-Item -LiteralPath $key).GetValue('')
                if ($directory) { $candidates += (Join-Path $directory 'python.exe') }
            }
        }
        $candidates += "$env:LOCALAPPDATA\Programs\Python\Python$tag\python.exe"
        $launcher = Get-Command py.exe -ErrorAction SilentlyContinue
        if ($launcher) {
            $path = & $launcher.Source "-$version" -c $probe 2>$null
            if ($LASTEXITCODE -eq 0 -and $path) { return $path }
        }
        foreach ($path in $candidates) {
            if (Test-Path -LiteralPath $path -PathType Leaf) {
                $found = & $path -c $probe
                if ($LASTEXITCODE -eq 0) { return $found }
            }
        }
    }
    $cmd = Get-Command python.exe -ErrorAction SilentlyContinue
    if ($cmd -and $cmd.Source -notlike '*\Microsoft\WindowsApps\*') {
        $found = & $cmd.Source -c $probe
        if ($LASTEXITCODE -eq 0) { return $found }
    }
}

try {
    $versionInfo = Get-ItemProperty 'HKLM:\SOFTWARE\Microsoft\Windows NT\CurrentVersion'
    $architecture = [System.Runtime.InteropServices.RuntimeInformation]::OSArchitecture.ToString()
    Write-Host "Host: Windows build $($versionInfo.CurrentBuildNumber), $architecture"
    if ($architecture -ne 'X64') { throw 'This native Windows launcher currently targets x64 hardware.' }
    if ([int]$versionInfo.CurrentBuildNumber -lt 22000) { throw 'This setup targets Windows 11 or newer desktop builds.' }
    if ($Check -and ($StartConfig -or $SmokeTest)) { throw 'Use -Check by itself.' }
    if (!(Test-Path home_telemetry\config_setup.py) -or !(Test-Path home_telemetry\setup_wizard.py)) {
        throw 'Extract the complete feature branch containing config init and the setup wizard.'
    }
    if (!(Test-Path -LiteralPath $venv)) {
        if (Test-Path .venv) { throw 'Incomplete or foreign .venv. Rename it and run setup again.' }
        if ($StartConfig) { throw 'Run setup once before starting the configured console.' }
        $python = Find-Python
        if ($Check) {
            if (!$python) { throw 'No compatible Python found. Run normal setup to install Python.' }
            & $python -B -c "import ssl, sqlite3, venv, ensurepip; print(ensurepip.version(), sqlite3.sqlite_version, ssl.OPENSSL_VERSION)"
            if ($LASTEXITCODE -ne 0) { throw 'Python runtime preflight failed.' }
            Write-Host 'Host preflight passed.'
            exit 0
        }
        if (!$python) {
            if (!(Get-Command winget.exe -ErrorAction SilentlyContinue)) {
                throw 'Install Python 3.12 x64 from python.org or install Microsoft App Installer (winget), then rerun.'
            }
            if ((Read-Host 'Install Python 3.12 x64 for your account with winget? [Y/n]') -match '^(n|no)$') {
                throw 'Python installation declined.'
            }
            & winget.exe install --id Python.Python.3.12 --exact --source winget --architecture x64 --scope user
            if ($LASTEXITCODE -ne 0) { throw "winget failed ($LASTEXITCODE). Install CPython 3.12 x64 and rerun." }
            $python = Find-Python
            if (!$python) { throw 'Python was installed but could not be located. Reopen the terminal and rerun.' }
        }
        Write-Host "Creating .venv using $python"
        & $python -m venv .venv
        if ($LASTEXITCODE -ne 0) { throw 'Virtual environment creation failed.' }
    }
    & $venv -c $probe
    if ($LASTEXITCODE -ne 0) { throw 'Use a Windows x64 CPython 3.11 or 3.12 venv. Rename the existing .venv to keep it and rerun.' }
    & $venv -c "import sys; print(sys.version); sys.exit(sys.prefix == sys.base_prefix)"
    if ($LASTEXITCODE -ne 0) { throw 'Expected an isolated virtual environment.' }
    if ($Check) {
        & $venv -B -c "import ssl, sqlite3, pip; print(pip.__version__, sqlite3.sqlite_version, ssl.OPENSSL_VERSION)"
        if ($LASTEXITCODE -ne 0) { throw 'Existing environment failed its runtime check.' }
        Write-Host 'Host preflight passed.'
        exit 0
    }
    if ($StartConfig) {
        & $venv -m home_telemetry.setup_wizard --start $StartConfig
    } else {
        & $venv -m ensurepip --upgrade
        if ($LASTEXITCODE -ne 0) { throw 'Unable to provision pip inside .venv.' }
        if ($SmokeTest) {
            & $venv -m home_telemetry.setup_wizard --smoke-test
        } else {
            & $venv -m home_telemetry.setup_wizard
        }
    }
    exit $LASTEXITCODE
} catch {
    Write-Host "Setup stopped: $_" -ForegroundColor Red
    exit 1
}
