@echo off
setlocal EnableExtensions
cd /d "%~dp0"
chcp 65001 >nul
title ChinaTelecom Course AFK
mode con cols=96 lines=28 >nul
color 0B
set PYTHONIOENCODING=utf-8
set PYTHONUTF8=1
"%SystemRoot%\System32\WindowsPowerShell\v1.0\powershell.exe" -NoProfile -ExecutionPolicy Bypass -Command ^
  "$sig='[System.Runtime.InteropServices.DllImport(\"kernel32.dll\")]public static extern System.IntPtr GetStdHandle(int nStdHandle);[System.Runtime.InteropServices.DllImport(\"kernel32.dll\")]public static extern bool GetConsoleMode(System.IntPtr hConsoleHandle,[ref]uint lpMode);[System.Runtime.InteropServices.DllImport(\"kernel32.dll\")]public static extern bool SetConsoleMode(System.IntPtr hConsoleHandle,uint dwMode);';" ^
  "$k=Add-Type -MemberDefinition $sig -Name NativeConsole -Namespace Win32 -PassThru;" ^
  "$h=$k::GetStdHandle(-10); $m=0; if($h -ne [System.IntPtr]::Zero -and $k::GetConsoleMode($h,[ref]$m)){ $n=($m -bor 0x80) -band (-bnot 0x60); [void]$k::SetConsoleMode($h,[uint32]$n) }" >nul 2>nul
cls

set "PAD=                "
echo.
echo %PAD%+------------------------------------------------------------+
echo %PAD%^|                 ChinaTelecom Course AFK                   ^|
echo %PAD%^|                    Unified Entry Point                    ^|
echo %PAD%^|                                                            ^|
echo %PAD%^|                 Starting launcher.py ...                   ^|
echo %PAD%+------------------------------------------------------------+
echo.

if not exist ".venv\Scripts\python.exe" (
    color 0C
    echo %PAD%Missing virtual environment: .venv\Scripts\python.exe
    echo %PAD%Create the virtual environment and install requirements.txt
    echo.
    pause
    exit /b 1
)

".venv\Scripts\python.exe" "launcher.py"
set "EXIT_CODE=%ERRORLEVEL%"
if not "%EXIT_CODE%"=="0" (
    color 0C
    echo.
    echo %PAD%Launcher exited with code %EXIT_CODE%.
    echo %PAD%Check log.txt for details.
    echo.
    pause
)
exit /b %EXIT_CODE%
