@echo off
rem Prepara o ambiente na primeira execucao e abre o aplicativo no navegador.
cd /d "%~dp0"

if not exist .venv (
    echo Criando o ambiente virtual...
    python -m venv .venv
    .venv\Scripts\python -m pip install --upgrade pip --quiet
    .venv\Scripts\pip install -r requirements.txt
)

.venv\Scripts\streamlit run app.py
pause
