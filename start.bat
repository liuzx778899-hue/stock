@echo off
title A-Stock Data Collector

echo ========================================
echo   A-Stock Data Collector - One-Click Start
echo ========================================
echo.

cd /d "%~dp0"

:: Check .env file
if not exist ".env" (
    echo [WARN] .env file not found!
    if exist ".env.example" (
        echo        Copying .env.example to .env...
        copy ".env.example" ".env" >nul
        echo.
        echo        ============================================
        echo        IMPORTANT: Please edit .env file now!
        echo        Enter your actual database credentials.
        echo        Then run this script again.
        echo        ============================================
        echo.
        notepad ".env"
        pause
        exit /b 0
    ) else (
        echo        Please create .env file with database config
        pause
        exit /b 1
    )
) else (
    echo [1/7] Config file .env found
)

:: Load environment variables from .env (Python will handle this)
:: Just verify DB_PASSWORD is available after Python loads
echo [2/7] Checking Python...

:: Check Python
where python >nul 2>nul
if %errorlevel% neq 0 (
    echo [ERROR] Python not found, please install Python first
    pause
    exit /b 1
)
echo       Python found

:: Check if Python dependencies installed
echo [3/7] Checking Python dependencies...
python -c "import fastapi" 2>nul
if %errorlevel% neq 0 (
    echo       Installing Python dependencies...
    pip install -r requirements.txt -q
    if %errorlevel% neq 0 (
        echo [ERROR] Failed to install Python dependencies
        pause
        exit /b 1
    )
    echo       Python dependencies installed
) else (
    echo       Python dependencies OK
)

:: Initialize database (auto create tables)
echo [4/7] Initializing database...
python main.py init
if %errorlevel% equ 0 (
    echo       Database initialized
) else (
    echo       Database already exists or init skipped
)

:: Check Node.js
where npm >nul 2>nul
if %errorlevel% neq 0 (
    echo [WARN] Node.js/npm not found, skipping frontend
    set NPM_EXISTS=0
) else (
    echo [5/7] Node.js/npm found
    set NPM_EXISTS=1

    :: Check if frontend dependencies installed
    if not exist "%~dp0frontend\node_modules" (
        echo       Installing frontend dependencies...
        cd /d "%~dp0frontend"
        npm install --silent
        if %errorlevel% neq 0 (
            echo [ERROR] Failed to install frontend dependencies
            pause
            exit /b 1
        )
        cd /d "%~dp0"
        echo       Frontend dependencies installed
    ) else (
        echo       Frontend dependencies OK
    )
)

:: Start Backend
echo [6/7] Starting Backend API...
start "Backend API - Port 8000" cmd /k "cd /d "%~dp0" && python web_app.py"

:: Wait for backend to start
timeout /t 3 /nobreak >nul

:: Start Frontend
if %NPM_EXISTS% equ 1 (
    echo [7/7] Starting Frontend Dev Server...
    start "Frontend Dev - Port 3000" cmd /k "cd /d "%~dp0frontend" && npm run dev"
) else (
    echo [7/7] Frontend skipped (Node.js not installed)
)

echo.
echo ========================================
echo   All services started!
echo ========================================
echo.
echo   Frontend: http://localhost:3000
echo   Backend:  http://localhost:8000
echo   API Docs: http://localhost:8000/docs
echo.
echo   Config:   .env file loaded
echo   Close this window will NOT stop services
echo   Please close the popup windows manually
echo.
pause