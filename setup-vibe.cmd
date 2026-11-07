@echo off
rem Universeller Einstieg fuer Windows: installiert Python bei Bedarf und startet den Setup.
setlocal
where py >nul 2>nul
if errorlevel 1 (
  echo Python 3 fehlt. Installation mit: winget install --id Python.Python.3.12 -e
  winget install --id Python.Python.3.12 -e
  if errorlevel 1 exit /b 1
)
py -3 "%~dp0scripts\setup-vibe.py" %*
exit /b %errorlevel%
