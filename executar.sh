#!/usr/bin/env bash
# Prepara o ambiente na primeira execução e abre o aplicativo no navegador.
set -e
cd "$(dirname "$0")"

if [ ! -d .venv ]; then
    echo "Criando o ambiente virtual..."
    python3 -m venv .venv
    ./.venv/bin/pip install --upgrade pip --quiet
    ./.venv/bin/pip install -r requirements.txt
fi

exec ./.venv/bin/streamlit run app.py
