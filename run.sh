#!/bin/bash
# =============================================================================
# App Reviews Analysis System - Run Script
# =============================================================================

# 스크립트 디렉토리로 이동
cd "$(dirname "$0")"

# 환경 변수 로드
if [ -f .env ]; then
    echo "✓ .env 파일을 찾았습니다."
    set -a
    source .env
    set +a
else
    echo "⚠ .env 파일을 찾을 수 없습니다. .env.example을 복사하세요."
    echo "  cp .env.example .env"
    exit 1
fi

# Python 경로 설정
if [ -z "$PYTHON_PATH" ]; then
    PYTHON_PATH="python"
    echo "⚠ PYTHON_PATH 미설정. 시스템 Python 사용"
fi

# Python 환경 확인
if [ -f "$PYTHON_PATH" ]; then
    echo "✓ Python 환경 확인: $PYTHON_PATH"
else
    if command -v $PYTHON_PATH &> /dev/null; then
        echo "✓ Python 환경 확인: $(which $PYTHON_PATH)"
    else
        echo "⚠ 지정된 Python을 찾을 수 없습니다: $PYTHON_PATH"
        echo "  시스템 Python을 사용합니다."
        PYTHON_PATH="python"
    fi
fi

# Flask 설정
export FLASK_APP=app
export FLASK_ENV=${FLASK_ENV:-development}
export FLASK_DEBUG=${FLASK_DEBUG:-true}

# 포트/호스트 설정
PORT=${FLASK_PORT:-5952}
HOST=${FLASK_HOST:-0.0.0.0}
WORKERS=${GUNICORN_WORKERS:-4}

# 기존 프로세스 종료
echo "Checking for process on port $PORT..."
PID=$(lsof -t -i:$PORT)
if [ ! -z "$PID" ]; then
    echo "Killing existing process on port $PORT (PID: $PID)..."
    kill -9 $PID
    sleep 2
fi

echo ""
echo "=========================================="
echo " App Reviews Analysis System"
echo "=========================================="
echo "서버 설정:"
echo "  - Python: $PYTHON_PATH"
echo "  - Host: $HOST"
echo "  - Port: $PORT"
echo "  - 환경: $FLASK_ENV"
echo "  - Debug: $FLASK_DEBUG"
echo ""

# 개발/운영 모드 분기
if [ "$FLASK_ENV" = "production" ]; then
    echo "🚀 Production 모드로 서버를 시작합니다 (Gunicorn)..."
    echo "   Workers: $WORKERS"
    echo "   접속 URL: http://$HOST:$PORT"
    echo ""
    $PYTHON_PATH -m gunicorn "app:create_app()" \
        --bind $HOST:$PORT \
        --workers $WORKERS \
        --access-logfile - \
        --error-logfile -
else
    echo "🔧 Development 모드로 서버를 시작합니다 (Flask)..."
    echo "   접속 URL: http://localhost:$PORT"
    echo "   Hot Reload: 활성화"
    echo ""
    $PYTHON_PATH -m flask run --host=$HOST --port=$PORT --reload
fi
