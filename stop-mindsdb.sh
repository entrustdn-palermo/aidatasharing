#!/bin/bash

# Stop MindsDB Server
echo "🛑 Stopping MindsDB server..."

PIDS=""

if [ -f /tmp/mindsdb.pid ]; then
    PIDS="$PIDS $(cat /tmp/mindsdb.pid)"
fi

for PORT in 47334 47335; do
    PORT_PIDS=$(lsof -tiTCP:$PORT -sTCP:LISTEN 2>/dev/null || true)
    if [ -n "$PORT_PIDS" ]; then
        PIDS="$PIDS $PORT_PIDS"
    fi
done

PROCESS_PIDS=$(pgrep -f "python -m mindsdb|mindsdb-server/bin/python.*multiprocessing-fork" 2>/dev/null || true)
if [ -n "$PROCESS_PIDS" ]; then
    PIDS="$PIDS $PROCESS_PIDS"
fi

PIDS=$(echo "$PIDS" | tr ' ' '\n' | grep -E '^[0-9]+$' | sort -u | tr '\n' ' ')

if [ -z "$PIDS" ]; then
    echo "⚠️  No MindsDB processes found"
    rm -f /tmp/mindsdb.pid
    exit 0
fi

echo "Found MindsDB processes: $PIDS"
kill $PIDS 2>/dev/null || true
sleep 2

REMAINING=""
for PID in $PIDS; do
    if kill -0 "$PID" 2>/dev/null; then
        REMAINING="$REMAINING $PID"
    fi
done

if [ -n "$REMAINING" ]; then
    echo "Force killing remaining processes:$REMAINING"
    kill -9 $REMAINING 2>/dev/null || true
fi

rm -f /tmp/mindsdb.pid
echo "✅ MindsDB server stopped"
