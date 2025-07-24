# Python 3.13 slim 이미지 사용
FROM python:3.13-slim

# 작업 디렉토리 설정
WORKDIR /app

# 시스템 패키지 업데이트 및 필요한 패키지 설치
RUN apt-get update && apt-get install -y \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# requirements.txt 복사 및 의존성 설치
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 애플리케이션 파일 복사
COPY rbtc_bot.py .

# 로그 디렉토리 생성
RUN mkdir -p /app/logs

# 비root 사용자 생성 (Railway 권장사항)
RUN adduser --disabled-password --gecos '' botuser && \
    chown -R botuser:botuser /app

# 사용자 전환
USER botuser

# 봇 실행 (unbuffered 출력)
CMD ["python", "-u", "rbtc_bot.py"]