@echo off
setlocal
set "PYTHONUTF8=1"
pushd "%~dp0.." || exit /b 1
powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0setup-windows.ps1" %*
set "result=%errorlevel%"
popd
exit /b %result%
