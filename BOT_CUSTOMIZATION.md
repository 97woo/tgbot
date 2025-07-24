# 텔레그램 봇 커스터마이징 가이드

## @BotFather를 통한 봇 설정 변경

### 1. 봇 프로필 사진 변경
```
/setuserpic
```
- @RSKorea_bot 선택
- 새 프로필 이미지 업로드

### 2. 봇 설명 변경
```
/setdescription
```
- @RSKorea_bot 선택
- 설명 입력 (예: RSK 네트워크 RBTC 에어드랍 봇)

### 3. 봇 소개 메시지 변경
```
/setabouttext
```
- @RSKorea_bot 선택
- 짧은 소개 입력 (예: RBTC 무료 에어드랍)

### 4. 봇 명령어 목록 설정
```
/setcommands
```
- @RSKorea_bot 선택
- 다음 형식으로 입력:
```
start - 봇 시작 및 도움말
create_wallet - 새 RSK 지갑 생성
set - 기존 지갑 주소 등록
wallet - 내 지갑 정보 확인
info - 봇 상태 확인
```

### 5. 봇 이름 변경
```
/setname
```
- @RSKorea_bot 선택
- 새 이름 입력 (예: RSK RBTC Drop Bot)

## 추가 설정

### 인라인 모드 비활성화 (선택사항)
```
/setinline
```
- 인라인 쿼리를 사용하지 않으려면 비활성화

### 그룹 추가 허용 설정
```
/setjoingroups
```
- Enable/Disable 선택

### 프라이버시 모드 설정
```
/setprivacy
```
- Enable: 봇이 명령어만 읽음
- Disable: 봇이 모든 메시지 읽음 (현재 설정 필요)