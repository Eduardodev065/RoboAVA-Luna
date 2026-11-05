@echo off
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo Ambiente Python nao encontrado. Consulte o README.md.
  pause
  exit /b 1
)
echo Cole a chave OpenAI UMA VEZ e pressione Enter. O texto nao aparece enquanto voce cola.
".venv\Scripts\python.exe" -m ava_py setup-key
pause
