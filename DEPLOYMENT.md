# RBTC Bot 배포 가이드

## 🚀 Docker & GitHub Actions CI/CD 설정

### 📋 사전 준비사항

1. **VPS 서버** (Ubuntu 20.04+ 권장)
2. **Docker & Docker Compose** 설치
3. **GitHub Secrets** 설정

### 🔧 로컬 개발 환경

#### Docker로 실행하기
```bash
# 빌드 및 실행
docker-compose up -d

# 로그 확인
docker-compose logs -f

# 중지
docker-compose down
```

### 🔐 GitHub Secrets 설정

GitHub 저장소 → Settings → Secrets and variables → Actions에서 추가:

| Secret 이름 | 설명 | 예시 |
|------------|------|------|
| `HOST` | VPS 서버 IP | `123.456.789.0` |
| `USERNAME` | SSH 사용자명 | `ubuntu` |
| `SSH_KEY` | SSH 개인키 | `-----BEGIN RSA PRIVATE KEY-----...` |
| `PORT` | SSH 포트 | `22` |
| `DEPLOY_PATH` | 배포 경로 | `/home/ubuntu/tgbot` |
| `ENV_FILE` | 환경변수 전체 내용 | `.env 파일 내용 전체` |

### 📦 VPS 서버 초기 설정

```bash
# Docker 설치
curl -fsSL https://get.docker.com -o get-docker.sh
sudo sh get-docker.sh
sudo usermod -aG docker $USER

# Docker Compose 설치
sudo curl -L "https://github.com/docker/compose/releases/latest/download/docker-compose-$(uname -s)-$(uname -m)" -o /usr/local/bin/docker-compose
sudo chmod +x /usr/local/bin/docker-compose

# 프로젝트 클론
git clone https://github.com/97woo/tgbot.git
cd tgbot

# wallets.json 파일 생성 (비어있는 파일)
echo "{}" > wallets.json
```

### 🚀 배포 프로세스

1. **코드 푸시**: `main` 브랜치에 푸시하면 자동 배포
2. **수동 배포**: GitHub Actions → Deploy RBTC Bot → Run workflow

### 📊 모니터링

```bash
# 컨테이너 상태 확인
docker ps

# 로그 확인
docker-compose logs -f rbtc-bot

# 실시간 로그
tail -f tx_bot.log
```

### 🔄 무중단 업데이트

봇은 자동으로 재시작되므로 수동 개입이 필요 없습니다:

```bash
# 수동 업데이트 (필요시)
git pull origin main
docker-compose pull
docker-compose up -d
```

### 🐛 트러블슈팅

#### 봇이 시작되지 않는 경우
```bash
# 컨테이너 로그 확인
docker-compose logs rbtc-bot

# 환경변수 확인
docker-compose exec rbtc-bot env
```

#### 권한 문제
```bash
# wallets.json 권한 설정
chmod 666 wallets.json
```

### 🔒 보안 주의사항

1. **절대 `.env` 파일을 커밋하지 마세요**
2. **프라이빗 키는 GitHub Secrets에만 저장**
3. **정기적으로 로그 파일 정리**

```bash
# 로그 정리 (cron으로 자동화 권장)
echo "" > tx_bot.log
```