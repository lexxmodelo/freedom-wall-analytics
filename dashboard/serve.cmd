@echo off
REM Local HTTP server for the dashboard. Run from the dashboard/ folder.
REM Browsers refuse fetch() from file:// pages, so the JSON data files won't
REM load unless the dashboard is served over HTTP. This is the simplest fix.

set PORT=8765
echo.
echo Serving dashboard on http://localhost:%PORT%/
echo   - Landing:       http://localhost:%PORT%/
echo   - Institutional: http://localhost:%PORT%/institutional/
echo   - Research:      http://localhost:%PORT%/research/
echo.
echo Press Ctrl+C to stop.
echo.
python -m http.server %PORT%
