#!/bin/sh
# Lance Ollama (si besoin) puis le bot KITT, et le relance s'il s'arrête.
# Utile dans une sandbox sans systemd. Arrêt : Ctrl+C ou « kill » du processus.
cd "$(dirname "$0")" || exit 1
export OLLAMA_NUM_THREADS=4
if ! curl -s http://127.0.0.1:11434/api/version >/dev/null 2>&1; then
  nohup ollama serve > "$HOME/.kitt-ollama.log" 2>&1 &
  sleep 5
fi
while true; do
  python3 kitt_telegram.py >> "$HOME/.kitt-bot.log" 2>&1
  echo "[$(date)] KITT s'est arrêté, nouvelle tentative dans 10 s" >> "$HOME/.kitt-bot.log"
  sleep 10
done
