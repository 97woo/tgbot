# 텔레그램 RBTC 봇 설정 가이드

## 1. 텔레그램 봇 생성

1. 텔레그램에서 [@BotFather](https://t.me/botfather) 검색
2. `/newbot` 명령어 입력
3. 봇 이름 입력 (예: RBTC Drop Bot)
4. 봇 username 입력 (예: rbtc_drop_bot) - 반드시 'bot'으로 끝나야 함
5. BotFather가 제공하는 토큰 복사

## 2. 환경 변수 설정

```bash
# .env 파일 편집
nano .env
```

다음 정보 입력:
- `TELEGRAM_BOT_TOKEN`: BotFather에서 받은 토큰
- `PRIVATE_KEY`: RSK 지갑의 프라이빗 키 (0x 포함)
- `ADMIN_USER_ID`: 본인의 텔레그램 user ID

### 텔레그램 User ID 확인 방법
1. [@userinfobot](https://t.me/userinfobot)에게 메시지 전송
2. 또는 [@raw_data_bot](https://t.me/raw_data_bot)에게 메시지 전송
3. 반환된 ID 값 확인

## 3. RSK 지갑 준비

### 옵션 1: 새 지갑 생성
```bash
python -c "from web3 import Web3; account = Web3().eth.account.create(); print(f'Address: {account.address}\nPrivate Key: {account.key.hex()}')"
```

### 옵션 2: 기존 지갑 사용
- MetaMask 또는 다른 지갑에서 프라이빗 키 export

## 4. RBTC 충전

1. RSK Testnet Faucet 사용:
   - https://faucet.rsk.co/
   - 지갑 주소 입력하여 테스트 RBTC 받기

2. Mainnet의 경우:
   - 거래소에서 RBTC 구매
   - 또는 BTC를 RSK 브릿지를 통해 RBTC로 변환

## 5. 봇 실행 테스트

```bash
# 필요한 패키지 설치
pip install pyTelegramBotAPI web3 python-dotenv

# 봇 실행
python rbtc_bot.py
```

## 6. 봇 명령어 테스트

텔레그램에서 봇 검색 후:
- `/start` - 봇 시작
- `/create_wallet` - 지갑 생성
- `/help` - 도움말
- 채팅 메시지 입력 - RBTC 드랍 확률 테스트

## 7. 설정 조정

`.env` 파일에서 조정 가능:
- `DROP_RATE`: 드랍 확률 (0.05 = 5%)
- `MAX_DAILY_AMOUNT`: 일일 최대 드랍량
- `COOLDOWN_SECONDS`: 유저별 쿨다운 시간

## 주의사항

1. **보안**: 프라이빗 키는 절대 공유하지 마세요
2. **테스트**: Mainnet 사용 전 반드시 Testnet에서 테스트
3. **금액**: RBTC는 BTC와 1:1 페깅되어 있어 높은 가치를 가집니다
4. **가스비**: RSK 네트워크 가스비 확인 필요

## 문제 해결

- 봇이 응답하지 않는 경우: 토큰 확인
- 트랜잭션 실패: 가스비 및 잔액 확인
- 권한 오류: ADMIN_USER_ID 확인