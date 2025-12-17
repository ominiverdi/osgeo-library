#!/bin/bash
# BGE-M3 Embedding Server - CPU Deployment
# BAAI/bge-m3: 568M params, 1024 dimensions
# Quantized Q8_0 for efficient CPU inference
#
# Usage:
#   ./servers/bge-m3-cpu.sh                    # Foreground
#   ./servers/bge-m3-cpu.sh &                  # Background
#   nohup ./servers/bge-m3-cpu.sh > /dev/null 2>&1 &  # Daemon

PORT=8094
MODEL_PATH="${MODEL_PATH:-models/bge-m3-Q8_0.gguf}"
THREADS="${THREADS:-4}"
LOG_FILE="${LOG_FILE:-logs/bge-m3-cpu.log}"

# Create log directory if needed
mkdir -p "$(dirname "$LOG_FILE")"

echo "Starting BGE-M3 embedding server..."
echo "  Model: $MODEL_PATH"
echo "  Port: $PORT"
echo "  Threads: $THREADS"
echo "  Log: $LOG_FILE"

exec llama-server \
  -m "$MODEL_PATH" \
  --embedding \
  --host 0.0.0.0 \
  --port $PORT \
  -c 2048 \
  -b 512 \
  -ub 512 \
  -np 1 \
  -t $THREADS \
  --alias "bge-m3" \
  2>&1 | tee -a "$LOG_FILE"
