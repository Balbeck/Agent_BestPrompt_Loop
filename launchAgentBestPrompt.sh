#!/usr/bin/env bash

cd "$(dirname "$0")"

VENV_DIR=".venv"

if [ ! -d "$VENV_DIR" ]; then
	echo "🐍 Creation du venv ($VENV_DIR)..."
	python3 -m venv "$VENV_DIR"
fi

echo "📦 Installation des dependances..."
"$VENV_DIR/bin/pip" install --quiet --upgrade pip
"$VENV_DIR/bin/pip" install --quiet -r requirements.txt

echo "🚀 Lancement 🤖 Agent [ Best Prompt ] Loop..."
exec "$VENV_DIR/bin/python" main.py
