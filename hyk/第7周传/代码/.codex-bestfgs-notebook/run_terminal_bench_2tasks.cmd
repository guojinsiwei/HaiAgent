@echo off
setlocal
cd /d "%~dp0"

if not defined DEEPSEEK_API_KEY (
  echo [ERROR] DEEPSEEK_API_KEY is not set in this cmd session.
  echo Run: set "DEEPSEEK_API_KEY=your-new-api-key"
  exit /b 2
)

set "PYTHONUTF8=1"

echo [TEST] Terminal-Bench 2: 2 tasks, 24 iterations / 80 tool calls per task
echo [TEST] Combined transition request, failed-transition shortcut, no full-task retry

python run_terminal_bench.py ^
  --provider deepseek ^
  --n-tasks 2 ^
  --n-concurrent 1 ^
  --max-retries 0 ^
  --max-iterations 24 ^
  --max-tool-calls 80 ^
  --model-timeout 90 ^
  --model-request-attempts 4 ^
  --model-parse-attempts 3 ^
  --agent-timeout-multiplier 8 ^
  --skip-image-pull

set "RUN_EXIT_CODE=%ERRORLEVEL%"
echo.
if "%RUN_EXIT_CODE%"=="0" (
  echo [DONE] Evaluation finished. The result path is printed above.
) else (
  echo [FAILED] Launcher exit code: %RUN_EXIT_CODE%
)
exit /b %RUN_EXIT_CODE%
