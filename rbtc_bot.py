#!/usr/bin/env python3
"""
RSK/Rootstock 체인 RBTC 드랍 텔레그램 봇
기능:
1. 지갑 등록: /set "wallet_address" 인라인 처리
2. 랜덤 드랍: 채팅시 일정 확률로 RBTC 전송
"""

import os
import json
import logging
import random
import re
from datetime import datetime, timedelta
from typing import Optional, Dict, Any
import telebot
from dotenv import load_dotenv
from web3 import Web3
from eth_account import Account

# 환경변수 로드
load_dotenv()

# 로깅 설정
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('tx_bot.log'),
        logging.StreamHandler()
    ]
)

class WalletManager:
    """지갑 주소 관리 클래스"""
    
    def __init__(self, wallet_file: str = "wallets.json"):
        self.wallet_file = wallet_file
        self.wallets = self._load_wallets()
    
    """지갑 데이터 로드"""
    def _load_wallets(self) -> Dict[str, str]:
        
        try:
            if os.path.exists(self.wallet_file):
                with open(self.wallet_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            return {}
        except Exception as e:
            logging.error(f"지갑 데이터 로드 실패: {e}")
            return {}
    
    """지갑 데이터 저장"""
    def _save_wallets(self) -> bool:
        
        try:
            with open(self.wallet_file, 'w', encoding='utf-8') as f:
                json.dump(self.wallets, f, indent=2, ensure_ascii=False)
            return True
        except Exception as e:
            logging.error(f"지갑 데이터 저장 실패: {e}")
            return False
    
    """지갑 주소 유효성 검사"""
    def is_valid_address(self, address: str) -> bool:
        
        try:
            # 이더리움 주소 형식 검사 (0x + 40자리 hex)
            pattern = r'^0x[a-fA-F0-9]{40}$'
            if not re.match(pattern, address):
                return False
            
            # Web3를 통한 체크섬 검증
            return Web3.is_address(address)
        except Exception:
            return False
    """지갑 주소 등록"""
    def set_wallet(self, user_id: str, wallet_address: str) -> bool:
       
        if not self.is_valid_address(wallet_address):
            return False
        
        # 체크섬 주소로 변환
        checksum_address = Web3.to_checksum_address(wallet_address)
        self.wallets[user_id] = checksum_address
        
        return self._save_wallets()
    """지갑 주소 조회"""
    def get_wallet(self, user_id: str) -> Optional[str]:
        
        return self.wallets.get(user_id)
    """지갑 주소 삭제"""
    def remove_wallet(self, user_id: str) -> bool:
        
        if user_id in self.wallets:
            del self.wallets[user_id]
            return self._save_wallets()
        return False
    """모든 지갑 주소 조회"""
    def get_all_wallets(self) -> Dict[str, str]:
        return self.wallets.copy()

class TransactionManager:
    """RSK 체인 트랜잭션 관리 클래스"""
    
    def __init__(self, rpc_url: str, private_key: str):
        self.rpc_url = rpc_url
        self.private_key = private_key
        self.w3 = Web3(Web3.HTTPProvider(rpc_url))
        
        # 지갑 계정 설정
        self.account = Account.from_key(private_key)
        
    def is_connected(self) -> bool:
        """RSK 체인 연결 상태 확인"""
        try:
            return self.w3.is_connected()
        except Exception as e:
            logging.error(f"RSK 체인 연결 실패: {e}")
            return False
    
    def should_drop(self, drop_rate: float) -> bool:
        """랜덤 드랍 여부 결정"""
        return random.random() < drop_rate
    
    def get_rbtc_balance(self, address: str) -> float:
        """RBTC 잔고 조회"""
        try:
            balance_wei = self.w3.eth.get_balance(
                Web3.to_checksum_address(address)
            )
            # RBTC는 18자리 소수점 (ETH와 동일)
            return balance_wei / (10 ** 18)
        except Exception as e:
            logging.error(f"RBTC 잔고 조회 실패: {e}")
            return 0.0
    
    def get_optimal_gas_estimate(self, to_address: str, amount: float) -> dict:
        """실제 전송 전 동적 가스 추정"""
        try:
            to_checksum = Web3.to_checksum_address(to_address)
            amount_wei = int(amount * (10 ** 18))  # RBTC 18자리 소수점
            
            # 현재 네트워크 상황으로 가스 추정 (RBTC 전송)
            estimated_gas = self.w3.eth.estimate_gas({
                'from': self.account.address,
                'to': to_checksum,
                'value': amount_wei
            })
            
            # RSK 기본 RBTC 전송: ~21,000 gas
            rsk_recommended = 21000
            
            # 추정값과 권장값 중 높은 값에 안전 마진 추가
            optimal_gas = max(estimated_gas, rsk_recommended)
            safe_gas = int(optimal_gas * 1.2)  # 20% 안전 마진
            
            # 최대 한도 설정 (과도한 가스 방지)
            max_gas = 50000  # RBTC 전송은 더 적은 가스 사용
            final_gas = min(safe_gas, max_gas)
            
            logging.info(f"가스 추정 결과: 추정={estimated_gas:,}, 권장={rsk_recommended:,}, 최종={final_gas:,}")
            
            return {
                'estimated': estimated_gas,
                'recommended': rsk_recommended,
                'final': final_gas,
                'margin': f"{((final_gas - estimated_gas) / estimated_gas * 100):.1f}%"
            }
            
        except Exception as e:
            logging.warning(f"동적 가스 추정 실패, 기본값 사용: {e}")
            # 추정 실패시 RSK 권장값 + 마진
            return {
                'estimated': 0,
                'recommended': 21000,
                'final': 25200,  # 21000 * 1.2
                'margin': '20.0%'
            }

    def send_rbtc(self, to_address: str, amount: float, retry_count: int = 0) -> Optional[str]:
        """RBTC 전송 (동적 가스 추정)"""
        try:
            to_checksum = Web3.to_checksum_address(to_address)
            amount_wei = int(amount * (10 ** 18))  # RBTC 18자리 소수점
            
            # 1단계: 현재 상황에 최적화된 가스 추정
            gas_info = self.get_optimal_gas_estimate(to_address, amount)
            optimal_gas = gas_info['final']
            
            # 2단계: 가스 가격 동적 조정 (재시도시 증가)
            # RSK는 더 낮은 가스 가격 사용
            base_gas_price = 0.06
            gas_price = base_gas_price + (retry_count * 0.02)
            
            # 3단계: 트랜잭션 구성 (가스 한도 명시적 설정)
            transaction = {
                'from': self.account.address,
                'to': to_checksum,
                'value': amount_wei,
                'gasPrice': self.w3.to_wei(str(gas_price), 'gwei'),
                'gas': optimal_gas,  # 동적으로 계산된 최적 가스
                'nonce': self.w3.eth.get_transaction_count(self.account.address, 'pending'),
                'chainId': 30  # RSK Mainnet (Testnet은 31)
            }
            
            # 트랜잭션 서명 및 전송
            signed_txn = self.w3.eth.account.sign_transaction(transaction, self.private_key)
            tx_hash = self.w3.eth.send_raw_transaction(signed_txn.rawTransaction)
            
            logging.info(f"RBTC 전송 성공: {amount} RBTC를 {to_address}로")
            logging.info(f"가스 정보: {gas_info['margin']} 마진, 한도 {optimal_gas:,}, 해시: {tx_hash.hex()}")
            return tx_hash.hex()
            
        except Exception as e:
            error_msg = str(e)
            
            # underpriced 오류 처리
            if "underpriced" in error_msg.lower() and retry_count < 3:
                logging.warning(f"Underpriced 오류, 재시도 {retry_count + 1}/3")
                import time
                time.sleep(2)
                return self.send_rbtc(to_address, amount, retry_count + 1)
            
            logging.error(f"RBTC 전송 실패 (재시도 {retry_count}회): {e}")
            return None

class RBTCDropBot:
    """USDC 드랍 텔레그램 봇"""
    
    def __init__(self):
        # 환경변수 로드
        self.bot_token = os.getenv('TELEGRAM_BOT_TOKEN')
        self.base_rpc = os.getenv('RPC_URL', 'https://public-node.testnet.rsk.co')
        self.private_key = os.getenv('PRIVATE_KEY')
        self.drop_rate = float(os.getenv('DROP_RATE', '0.05'))  # 5%
        self.max_daily_amount = float(os.getenv('MAX_DAILY_AMOUNT', '0.00003125'))  # 0.00003125 RBTC (~5000 KRW at 160M KRW/BTC)
        self.admin_user_id = os.getenv('ADMIN_USER_ID')
        
        
        if not self.bot_token:
            raise ValueError("TELEGRAM_BOT_TOKEN이 설정되지 않았습니다.")
        
        # 봇 초기화
        self.bot = telebot.TeleBot(self.bot_token)
        self.wallet_manager = WalletManager()
        
        # 트랜잭션 매니저 초기화 (private_key가 있을 때만)
        if self.private_key:
            self.tx_manager = TransactionManager(
                self.base_rpc, 
                self.private_key
            )
        else:
            self.tx_manager = None
            logging.warning("PRIVATE_KEY가 설정되지 않았습니다.")
        
        # 일일 전송량 추적
        self.daily_sent = {}
        
        # [modify] 전송 쿨타임 관리 (새로 추가)
        self.last_transaction_time = {}  # [modify] 사용자별 마지막 전송 시간
        self.cooldown_seconds = float(os.getenv('COOLDOWN_SECONDS', '60'))  # 기본 60초 쿨타임
        
        # 핸들러 설정
        self.setup_handlers()
    
    def setup_handlers(self):
        """메시지 핸들러 설정"""
        
        @self.bot.message_handler(commands=['start'])
        def handle_start(message):
            """시작 명령어"""
            # 사용자 ID 로깅 (임시)
            user_id = message.from_user.id
            username = message.from_user.username or "No username"
            logging.info(f"User ID: {user_id}, Username: @{username}")
            
            welcome_text = f"""
🎯 RSK RBTC 드랍 봇에 오신 것을 환영합니다!

💰 주요 기능:
• /set 0x주소 - 지갑 주소 등록
• /wallet - 내 지갑 정보 확인
• /info - 봇 상태 및 설정 확인

🎲 RBTC 에어드랍:
• 채팅 메시지 작성시 {self.drop_rate*100:.1f}% 확률로 자동 드랍
• 1회 드랍량: 0.00000625 RBTC
• 일일 최대: 0.00003125 RBTC
• 쿨다운: {self.cooldown_seconds}초

💡 시작하려면 /set 명령어로 지갑을 등록하세요!
            """
            self.bot.reply_to(message, welcome_text)
        
        @self.bot.message_handler(commands=['create_wallet'])
        def handle_create_wallet(message):
            """새 지갑 생성"""
            # 그룹 채팅에서는 비활성화
            if message.chat.type in ['group', 'supergroup']:
                self.bot.reply_to(message, "❌ 보안을 위해 그룹에서는 지갑 생성이 불가합니다. 개인 채팅에서 사용해주세요.")
                return
            
            try:
                # 새 지갑 생성
                from web3 import Web3
                w3 = Web3()
                account = w3.eth.account.create()
                
                user_id = str(message.from_user.id)
                user_name = f"@{message.from_user.username}" if message.from_user.username else message.from_user.first_name or "Unknown"
                
                # 지갑 저장
                if self.wallet_manager.set_wallet(user_id, account.address):
                    response_text = f"""✅ 새 지갑이 생성되었습니다!

💳 주소: `{account.address}`
🔑 Private Key: `{account.key.hex()}`

⚠️ **중요**: Private Key를 안전하게 보관하세요!
이 메시지는 곧 삭제됩니다."""
                    
                    # 메시지 전송 후 10초 뒤 삭제
                    sent_msg = self.bot.reply_to(message, response_text, parse_mode='Markdown')
                    import time
                    time.sleep(10)
                    try:
                        self.bot.delete_message(message.chat.id, sent_msg.message_id)
                        self.bot.delete_message(message.chat.id, message.message_id)
                    except:
                        pass
                else:
                    self.bot.reply_to(message, "❌ 지갑 생성 실패")
            except Exception as e:
                logging.error(f"지갑 생성 오류: {e}")
                self.bot.reply_to(message, "❌ 지갑 생성 중 오류가 발생했습니다.")
        
        @self.bot.message_handler(commands=['set'])
        def handle_set_wallet(message):
            """지갑 주소 설정 (인라인 처리)"""
            # 그룹 채팅에서는 비활성화
            if message.chat.type in ['group', 'supergroup']:
                self.bot.reply_to(message, "❌ 보안을 위해 그룹에서는 지갑 등록이 불가합니다. 개인 채팅에서 사용해주세요.")
                return
            
            user_id = str(message.from_user.id)
            user_name = message.from_user.first_name or message.from_user.username or "Unknown"
            
            # 지갑 주소 추출
            wallet_address = self.parse_set_command(message.text)
            
            if not wallet_address:
                self.bot.reply_to(message, "❌ 사용법: /set 0x1234...")
                return
            
            # 인라인 처리: 즉시 검증 및 저장
            if self.wallet_manager.set_wallet(user_id, wallet_address):
                success_text = "✅ 등록완료했습니다!"  # [modify] 메시지 간소화
                self.bot.reply_to(message, success_text)
                logging.info(f"지갑 등록 성공: {user_name} ({user_id}) -> {wallet_address}")
            else:
                self.bot.reply_to(message, "❌ 유효하지 않은 지갑 주소입니다. Base 체인 주소를 확인해주세요.")
        
        @self.bot.message_handler(commands=['wallet'])
        def handle_wallet_info(message):
            """내 지갑 정보 조회"""
            user_id = str(message.from_user.id)
            wallet = self.wallet_manager.get_wallet(user_id)
            
            if wallet:
                self.bot.reply_to(message, f"💳 등록된 지갑: {wallet}")
            else:
                self.bot.reply_to(message, "❌ 등록된 지갑이 없습니다. /set 명령어로 지갑을 등록해주세요.")
        
        @self.bot.message_handler(commands=['info'])
        def handle_info(message):
            """봇 정보 및 설정"""
            today = datetime.now().date().isoformat()
            today_sent = self.daily_sent.get(today, 0)
            
            info_text = f"""
📊 봇 설정 정보:

🎲 드랍 확률: 비밀 🤫
💰 하루 최대: {self.max_daily_amount:.8f} RBTC
📈 오늘 전송: {today_sent:.8f} RBTC
👥 등록 지갑: {len(self.wallet_manager.get_all_wallets())}개
⏰ 전송 쿨타임: {int(self.cooldown_seconds)}초

🌐 체인: Rootstock Network
            """
            self.bot.reply_to(message, info_text)
        
        
        @self.bot.message_handler(func=lambda message: True)
        def handle_all_messages(message):
            """모든 메시지 처리 - 랜덤 드랍 트리거"""
            if message.from_user:
                user_id = str(message.from_user.id)
                user_name = f"@{message.from_user.username}" if message.from_user.username else message.from_user.first_name or "Unknown"
                
                # 디버깅: 모든 메시지 로깅
                logging.info(f"메시지 수신 - 채팅 타입: {message.chat.type}, 채팅: {message.chat.title if hasattr(message.chat, 'title') else 'Private'}, 사용자: {user_name}, 메시지: {message.text[:50] if message.text else 'No text'}")
                
                # 메시지가 명령어인 경우 무시
                if message.text and message.text.startswith('/'):
                    return
                
                # 랜덤 드랍 처리
                self.process_message_drop(message, user_id, user_name)
    
    @staticmethod
    def parse_set_command(command_text: str) -> Optional[str]:
        """지갑 설정 명령어 파싱"""
        if not command_text:
            return None
        
        # /set 다음에 오는 주소 추출 (공백으로 구분)
        parts = command_text.strip().split()
        if len(parts) >= 2 and parts[0] == '/set':
            # /set 다음의 모든 부분을 주소로 간주
            wallet_address = ' '.join(parts[1:]).strip()
            # 쌍따옴표가 있다면 제거
            if wallet_address.startswith('"') and wallet_address.endswith('"'):
                wallet_address = wallet_address[1:-1]
            return wallet_address
        
        return None
    
    def process_message_drop(self, message, user_id: str, user_name: str):
        """메시지별 드랍 처리"""
        logging.info(f"드랍 처리 시작 - 사용자: {user_name} ({user_id}), 채팅 타입: {message.chat.type}")
        
        # 개인 채팅에서는 드랍 비활성화
        if message.chat.type == 'private':
            logging.info(f"개인 채팅에서는 드랍이 비활성화됨")
            return
        
        # [modify] 메시지 길이 체크 (5글자 이상)
        if not message.text or len(message.text) < 5:
            logging.info(f"메시지 길이 미달: {len(message.text) if message.text else 0}자")
            return  # 5글자 미만시 드랍 없음
        
        # 지갑이 등록되어 있는지 확인
        wallet_address = self.wallet_manager.get_wallet(user_id)
        if not wallet_address:
            logging.info(f"지갑 미등록 사용자: {user_name}")
            return  # 지갑 미등록시 드랍 없음
        
        # [modify] 쿨타임 체크 (새로 추가)
        now = datetime.now()  # [modify]
        last_tx_time = self.last_transaction_time.get(user_id)  # [modify]
        if last_tx_time:  # [modify]
            time_diff = (now - last_tx_time).total_seconds()  # [modify]
            if time_diff < self.cooldown_seconds:  # [modify]
                logging.info(f"쿨타임: {user_name} ({user_id}) - {self.cooldown_seconds - time_diff:.1f}초 남음")  # [modify]
                return  # [modify] 쿨타임 중
        
        # 일일 한도 확인
        today = datetime.now().date().isoformat()
        today_sent = self.daily_sent.get(today, 0)
        
        if today_sent >= self.max_daily_amount:
            return  # 일일 한도 초과
        
        # 랜덤 드랍 여부 결정
        if not (self.tx_manager and self.tx_manager.should_drop(self.drop_rate)):
            logging.info(f"랜덤 드랍 실패 - 확률: {self.drop_rate*100}%")
            return  # 드랍 안함
        
        logging.info(f"🎉 드랍 당첨! 사용자: {user_name}, 지갑: {wallet_address[:10]}...")
        
        # 드랍 금액 (0.00000001 ~ 0.00000005 RBTC - ~$0.0016 ~ $0.008)
        drop_amount = 0.00000625  # 고정 금액: 0.00000625 RBTC (~1,000원)
        
        # 일일 한도 체크
        if today_sent + drop_amount > self.max_daily_amount:
            drop_amount = self.max_daily_amount - today_sent
            if drop_amount < 0.00000001:
                return  # 너무 적으면 드랍 안함
        
        # RBTC 전송
        tx_hash = self.tx_manager.send_rbtc(
            wallet_address, 
            drop_amount
        )
        
        if tx_hash:
            # 일일 전송량 업데이트
            self.daily_sent[today] = today_sent + drop_amount
            
            # [modify] 쿨타임 업데이트 (새로 추가)
            self.last_transaction_time[user_id] = now  # [modify]
            
            # 드랍 알림
            # RSK 메인넷 익스플로러 URL
            explorer_url = f"https://explorer.rsk.co/tx/{tx_hash}"
            
            drop_text = f"""
💸 RBTC 드랍! 🎉

👤 {user_name}
💰 {drop_amount:.8f} RBTC
🔗 [트랜잭션 확인]({explorer_url})
            """  # [modify] 쿨타임 정보 제거
            
            self.bot.reply_to(message, drop_text, parse_mode='Markdown', disable_web_page_preview=True)
            logging.info(f"드랍 성공: {user_name} ({user_id}) -> {drop_amount:.8f} RBTC (쿨타임 {self.cooldown_seconds}초 시작)")  # [modify]
    
    def run(self):
        """봇 실행"""
        logging.info("RBTC 드랍 봇 시작")
        logging.info(f"드랍 확률: {self.drop_rate*100:.1f}%, 일일 한도: {self.max_daily_amount:.8f} RBTC")
        
        try:
            self.bot.infinity_polling(timeout=10, long_polling_timeout=5)
        except Exception as e:
            logging.error(f"봇 실행 오류: {e}")
        finally:
            logging.info("RBTC 드랍 봇 종료")
    

def main():
    """메인 함수"""
    try:
        bot = RBTCDropBot()
        bot.run()
    except Exception as e:
        logging.error(f"메인 함수 오류: {e}")

if __name__ == "__main__":
    main() 