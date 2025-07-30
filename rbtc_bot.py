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
import time
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List
import telebot
from dotenv import load_dotenv
from web3 import Web3
from eth_account import Account
import requests
import threading

# 환경변수 로드
load_dotenv()

# 로깅 설정
from logging.handlers import RotatingFileHandler

# 로그 핸들러 설정
log_handler = RotatingFileHandler(
    'tx_bot.log',
    maxBytes=10*1024*1024,  # 10MB
    backupCount=5  # 최대 5개 백업 파일
)

logging.basicConfig(
    level=logging.INFO,  # INFO 레벨로 복원
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        log_handler,
        logging.StreamHandler()
    ]
)

# urllib3 로그 비활성화
logging.getLogger('urllib3').setLevel(logging.WARNING)
# telebot 로그 레벨 조정
logging.getLogger('TeleBot').setLevel(logging.WARNING)

class LastWinnerTracker:
    """채팅방별 마지막 당첨자 추적 (간단한 라운드 로빈)"""
    
    def __init__(self):
        self.last_winners = {}  # {chat_id: last_winner_user_id}
        self.lock = threading.Lock()
    
    def can_receive_drop(self, chat_id: int, user_id: str, total_users: int = 4) -> bool:
        """사용자가 드랍을 받을 수 있는지 확인
        - 마지막 당첨자와 같으면 False
        - 채팅방에 3명 이하면 항상 False (드랍 금지)
        """
        with self.lock:
            # 채팅방에 사용자가 3명 이하면 드랍 금지
            if total_users <= 3:
                return False
            
            # 마지막 당첨자가 없으면 받을 수 있음
            if chat_id not in self.last_winners:
                return True
            
            # 마지막 당첨자와 다르면 받을 수 있음
            return self.last_winners[chat_id] != user_id
    
    def update_winner(self, chat_id: int, user_id: str):
        """당첨자 업데이트"""
        with self.lock:
            self.last_winners[chat_id] = user_id
            logging.info(f"마지막 당첨자 업데이트 - 채팅방: {chat_id}, 사용자: {user_id}")
    
    def get_last_winner(self, chat_id: int) -> Optional[str]:
        """마지막 당첨자 조회"""
        with self.lock:
            return self.last_winners.get(chat_id)
    
    def save_to_dict(self) -> Dict:
        """Gist 저장용 딕셔너리로 변환"""
        with self.lock:
            return self.last_winners.copy()
    
    def load_from_dict(self, data: Dict):
        """Gist에서 로드한 데이터 적용"""
        with self.lock:
            self.last_winners = data

class WalletManager:
    """GitHub Gist를 사용한 지갑 주소 관리 클래스"""
    
    def __init__(self, gist_token: str = None, gist_id: str = None):
        self.gist_token = gist_token or os.getenv('GITHUB_GIST_TOKEN')
        self.gist_id = gist_id or os.getenv('GITHUB_GIST_ID')
        
        # Gist 사용 불가시 로컬 파일 백업
        self.use_local = not (self.gist_token and self.gist_id)
        self.wallet_file = "wallets.json"
        
        # 지갑 데이터 로드
        self.wallets = self._load_wallets()
    
    def _load_wallets(self) -> Dict[str, str]:
        """지갑 데이터 로드 (Gist 또는 로컬)"""
        if self.use_local:
            try:
                if os.path.exists(self.wallet_file):
                    with open(self.wallet_file, 'r', encoding='utf-8') as f:
                        return json.load(f)
            except Exception as e:
                logging.error(f"로컬 지갑 데이터 로드 실패: {e}")
            return {}
        
        # GitHub Gist에서 로드
        try:
            headers = {
                'Authorization': f'token {self.gist_token}',
                'Accept': 'application/vnd.github.v3+json'
            }
            response = requests.get(
                f'https://api.github.com/gists/{self.gist_id}',
                headers=headers
            )
            
            if response.status_code == 200:
                gist_data = response.json()
                if 'wallets.json' in gist_data['files']:
                    content = gist_data['files']['wallets.json']['content']
                    return json.loads(content)
            else:
                logging.error(f"Gist 로드 실패: {response.status_code}")
        except Exception as e:
            logging.error(f"Gist 데이터 로드 실패: {e}")
        
        return {}
    
    def _save_wallets(self) -> bool:
        """지갑 데이터 저장 (Gist 또는 로컬)"""
        if self.use_local:
            try:
                with open(self.wallet_file, 'w', encoding='utf-8') as f:
                    json.dump(self.wallets, f, indent=2, ensure_ascii=False)
                return True
            except Exception as e:
                logging.error(f"로컬 지갑 데이터 저장 실패: {e}")
                return False
        
        # GitHub Gist에 저장
        try:
            headers = {
                'Authorization': f'token {self.gist_token}',
                'Accept': 'application/vnd.github.v3+json'
            }
            
            # 기존 Gist 내용 가져오기
            response = requests.get(
                f'https://api.github.com/gists/{self.gist_id}',
                headers=headers
            )
            
            files = {}
            if response.status_code == 200:
                gist_data = response.json()
                # 기존 파일들 유지
                for filename in ['wallets.json', 'daily_sent.json', 'limit_notifications.json', 'last_winners.json', 'blacklist.json']:
                    if filename in gist_data['files']:
                        files[filename] = {'content': gist_data['files'][filename]['content']}
            
            # wallets.json 업데이트
            files['wallets.json'] = {'content': json.dumps(self.wallets, indent=2, ensure_ascii=False)}
            
            # Gist 업데이트
            update_response = requests.patch(
                f'https://api.github.com/gists/{self.gist_id}',
                headers=headers,
                json={'files': files}
            )
            
            if update_response.status_code == 200:
                logging.info("Gist에 지갑 데이터 저장 성공")
                return True
            else:
                logging.error(f"Gist 저장 실패: {update_response.status_code}")
                return False
        except Exception as e:
            logging.error(f"Gist 데이터 저장 실패: {e}")
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
    
    def load_daily_sent(self) -> Dict[str, float]:
        """Gist에서 일일 전송량 로드"""
        if self.use_local:
            try:
                if os.path.exists('daily_sent.json'):
                    with open('daily_sent.json', 'r') as f:
                        return json.load(f)
            except:
                pass
            return {}
        
        # Gist에서 로드
        try:
            headers = {
                'Authorization': f'token {self.gist_token}',
                'Accept': 'application/vnd.github.v3+json'
            }
            response = requests.get(
                f'https://api.github.com/gists/{self.gist_id}',
                headers=headers
            )
            
            if response.status_code == 200:
                gist_data = response.json()
                if 'daily_sent.json' in gist_data['files']:
                    content = gist_data['files']['daily_sent.json']['content']
                    return json.loads(content)
        except:
            pass
        
        return {}
    
    def save_daily_sent(self, daily_sent: Dict[str, float]) -> bool:
        """Gist에 일일 전송량 저장"""
        if self.use_local:
            try:
                with open('daily_sent.json', 'w') as f:
                    json.dump(daily_sent, f)
                return True
            except:
                return False
        
        # Gist에 저장
        try:
            headers = {
                'Authorization': f'token {self.gist_token}',
                'Accept': 'application/vnd.github.v3+json'
            }
            
            # 기존 Gist 내용 가져오기
            response = requests.get(
                f'https://api.github.com/gists/{self.gist_id}',
                headers=headers
            )
            
            if response.status_code == 200:
                gist_data = response.json()
                files = gist_data['files']
                
                # daily_sent.json 추가/업데이트
                files['daily_sent.json'] = {
                    'content': json.dumps(daily_sent, indent=2)
                }
                
                # Gist 업데이트
                update_data = {'files': files}
                update_response = requests.patch(
                    f'https://api.github.com/gists/{self.gist_id}',
                    headers=headers,
                    json=update_data
                )
                
                return update_response.status_code == 200
        except:
            pass
        
        return False
    
    def load_limit_notifications(self) -> Dict[str, List[int]]:
        """한도 도달 알림 기록 로드"""
        if self.use_local:
            try:
                if os.path.exists('limit_notifications.json'):
                    with open('limit_notifications.json', 'r') as f:
                        return json.load(f)
            except:
                pass
            return {}
        
        # Gist에서 로드
        try:
            headers = {
                'Authorization': f'token {self.gist_token}',
                'Accept': 'application/vnd.github.v3+json'
            }
            response = requests.get(
                f'https://api.github.com/gists/{self.gist_id}',
                headers=headers
            )
            
            if response.status_code == 200:
                gist_data = response.json()
                if 'limit_notifications.json' in gist_data['files']:
                    content = gist_data['files']['limit_notifications.json']['content']
                    return json.loads(content)
        except:
            pass
        
        return {}
    
    def save_limit_notifications(self, notifications: Dict[str, List[int]]) -> bool:
        """한도 도달 알림 기록 저장"""
        if self.use_local:
            try:
                with open('limit_notifications.json', 'w') as f:
                    json.dump(notifications, f)
                return True
            except:
                return False
        
        # Gist에 저장
        try:
            headers = {
                'Authorization': f'token {self.gist_token}',
                'Accept': 'application/vnd.github.v3+json'
            }
            
            # 기존 Gist 내용 가져오기
            response = requests.get(
                f'https://api.github.com/gists/{self.gist_id}',
                headers=headers
            )
            
            if response.status_code == 200:
                gist_data = response.json()
                files = gist_data['files']
                
                # limit_notifications.json 추가/업데이트
                files['limit_notifications.json'] = {
                    'content': json.dumps(notifications, indent=2)
                }
                
                # Gist 업데이트
                update_data = {'files': files}
                update_response = requests.patch(
                    f'https://api.github.com/gists/{self.gist_id}',
                    headers=headers,
                    json=update_data
                )
                
                return update_response.status_code == 200
        except:
            pass
        
        return False
    
    def load_last_winners(self) -> Dict[int, str]:
        """Gist에서 마지막 당첨자 정보 로드"""
        if self.use_local:
            try:
                if os.path.exists('last_winners.json'):
                    with open('last_winners.json', 'r') as f:
                        data = json.load(f)
                        # 키를 int로 변환
                        return {int(k): v for k, v in data.items()}
            except:
                pass
            return {}
        
        # Gist에서 로드
        try:
            headers = {
                'Authorization': f'token {self.gist_token}',
                'Accept': 'application/vnd.github.v3+json'
            }
            response = requests.get(
                f'https://api.github.com/gists/{self.gist_id}',
                headers=headers
            )
            
            if response.status_code == 200:
                gist_data = response.json()
                if 'last_winners.json' in gist_data['files']:
                    content = gist_data['files']['last_winners.json']['content']
                    data = json.loads(content) if content else {}
                    # 키를 int로 변환
                    return {int(k): v for k, v in data.items()}
        except:
            pass
        
        return {}
    
    def load_blacklist(self) -> List[str]:
        """Gist에서 블랙리스트 로드"""
        if self.use_local:
            try:
                if os.path.exists('blacklist.json'):
                    with open('blacklist.json', 'r') as f:
                        return json.load(f)
            except:
                pass
            return []
        
        # Gist에서 로드
        try:
            headers = {
                'Authorization': f'token {self.gist_token}',
                'Accept': 'application/vnd.github.v3+json'
            }
            response = requests.get(
                f'https://api.github.com/gists/{self.gist_id}',
                headers=headers
            )
            
            if response.status_code == 200:
                gist_data = response.json()
                if 'blacklist.json' in gist_data['files']:
                    content = gist_data['files']['blacklist.json']['content']
                    return json.loads(content) if content else []
        except:
            pass
        
        return []
    
    def load_drop_history(self) -> List[Dict]:
        """Gist에서 드랍 이력 로드"""
        if self.use_local:
            try:
                if os.path.exists('drop_history.json'):
                    with open('drop_history.json', 'r') as f:
                        return json.load(f)
            except:
                pass
            return []
        
        # Gist에서 로드
        try:
            headers = {
                'Authorization': f'token {self.gist_token}',
                'Accept': 'application/vnd.github.v3+json'
            }
            response = requests.get(
                f'https://api.github.com/gists/{self.gist_id}',
                headers=headers
            )
            
            if response.status_code == 200:
                gist_data = response.json()
                if 'drop_history.json' in gist_data['files']:
                    content = gist_data['files']['drop_history.json']['content']
                    return json.loads(content) if content else []
        except:
            pass
        
        return []
    
    def save_drop_history(self, history: List[Dict]) -> bool:
        """드랍 이력 저장"""
        if self.use_local:
            try:
                with open('drop_history.json', 'w') as f:
                    json.dump(history, f, indent=2, ensure_ascii=False)
                return True
            except:
                return False
        
        # Gist에 저장
        try:
            headers = {
                'Authorization': f'token {self.gist_token}',
                'Accept': 'application/vnd.github.v3+json'
            }
            
            # 기존 Gist 내용 가져오기
            response = requests.get(
                f'https://api.github.com/gists/{self.gist_id}',
                headers=headers
            )
            
            files = {}
            if response.status_code == 200:
                gist_data = response.json()
                # 기존 파일들 유지
                for filename in ['wallets.json', 'daily_sent.json', 'limit_notifications.json', 'last_winners.json', 'blacklist.json', 'drop_history.json']:
                    if filename in gist_data['files']:
                        files[filename] = {'content': gist_data['files'][filename]['content']}
            
            # 드랍 이력 업데이트
            files['drop_history.json'] = {'content': json.dumps(history, indent=2, ensure_ascii=False)}
            
            # Gist 업데이트
            update_response = requests.patch(
                f'https://api.github.com/gists/{self.gist_id}',
                headers=headers,
                json={'files': files}
            )
            
            return update_response.status_code == 200
        except:
            return False
    
    def save_blacklist(self, blacklist: List[str]) -> bool:
        """블랙리스트 저장"""
        if self.use_local:
            try:
                with open('blacklist.json', 'w') as f:
                    json.dump(blacklist, f)
                return True
            except:
                return False
        
        # Gist에 저장
        try:
            headers = {
                'Authorization': f'token {self.gist_token}',
                'Accept': 'application/vnd.github.v3+json'
            }
            
            # 기존 Gist 내용 가져오기
            response = requests.get(
                f'https://api.github.com/gists/{self.gist_id}',
                headers=headers
            )
            
            files = {}
            if response.status_code == 200:
                gist_data = response.json()
                # 기존 파일들 유지
                for filename in ['wallets.json', 'daily_sent.json', 'limit_notifications.json', 'last_winners.json', 'blacklist.json']:
                    if filename in gist_data['files']:
                        files[filename] = {'content': gist_data['files'][filename]['content']}
            
            # 블랙리스트 업데이트
            files['blacklist.json'] = {'content': json.dumps(blacklist, indent=2)}
            
            # Gist 업데이트
            update_response = requests.patch(
                f'https://api.github.com/gists/{self.gist_id}',
                headers=headers,
                json={'files': files}
            )
            
            return update_response.status_code == 200
        except:
            return False
    
    def save_last_winners(self, last_winners: Dict[int, str]) -> bool:
        """마지막 당첨자 정보 저장"""
        if self.use_local:
            try:
                with open('last_winners.json', 'w') as f:
                    json.dump(last_winners, f)
                return True
            except:
                return False
        
        # Gist에 저장
        try:
            headers = {
                'Authorization': f'token {self.gist_token}',
                'Accept': 'application/vnd.github.v3+json'
            }
            
            # 기존 Gist 내용 가져오기
            response = requests.get(
                f'https://api.github.com/gists/{self.gist_id}',
                headers=headers
            )
            
            files = {}
            if response.status_code == 200:
                gist_data = response.json()
                # 기존 파일들 유지
                for filename in ['wallets.json', 'daily_sent.json', 'limit_notifications.json', 'last_winners.json']:
                    if filename in gist_data['files']:
                        files[filename] = {'content': gist_data['files'][filename]['content']}
            
            # 마지막 당첨자 정보 업데이트
            files['last_winners.json'] = {'content': json.dumps(last_winners, indent=2)}
            
            # Gist 업데이트
            update_response = requests.patch(
                f'https://api.github.com/gists/{self.gist_id}',
                headers=headers,
                json={'files': files}
            )
            
            return update_response.status_code == 200
        except:
            return False

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
            # RSK 메인넷 최소 가스 가격 (로벨 업그레이드 이후)
            min_gas_price = 0.0237  # 0.0237 Gwei (로벨 업그레이드 이후 최소값)
            base_gas_price = min_gas_price * 1.1  # 최소값보다 10% 높게 설정
            gas_price = base_gas_price + (retry_count * 0.01)  # 재시도시 0.01 Gwei씩 증가
            
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
        self.max_daily_amount = float(os.getenv('MAX_DAILY_AMOUNT', '0.00003125'))  # 0.00003125 RBTC (~5000원 at 160M KRW/BTC)
        self.admin_user_id = os.getenv('ADMIN_USER_ID')
        self.bot_wallet_address = os.getenv('BOT_WALLET_ADDRESS')
        
        
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
        
        # 일일 전송량 추적 (Gist에서 로드)
        self.daily_sent = self.wallet_manager.load_daily_sent()
        
        # 일일 한도 알림 기록 로드
        self.limit_notifications = self.wallet_manager.load_limit_notifications()
        
        # [modify] 전송 쿨타임 관리 (새로 추가)
        self.last_transaction_time = {}  # [modify] 사용자별 마지막 전송 시간
        self.cooldown_seconds = float(os.getenv('COOLDOWN_SECONDS', '60'))  # 기본 60초 쿨타임
        
        # 라운드 로빈 추적
        self.last_winner_tracker = LastWinnerTracker()
        last_winners_data = self.wallet_manager.load_last_winners()
        self.last_winner_tracker.load_from_dict(last_winners_data)
        
        # 블랙리스트 로드
        self.blacklist = self.wallet_manager.load_blacklist()
        logging.info(f"블랙리스트 로드: {len(self.blacklist)}명")
        
        # 드랍 이력 로드
        self.drop_history = self.wallet_manager.load_drop_history()
        logging.info(f"드랍 이력 로드: {len(self.drop_history)}건")
        
        # 핸들러 설정
        self.setup_handlers()
        
        # 봇 정보 저장
        self.bot_info = self.bot.get_me()
        
        # 설정 출력
        logging.info(f"=== 봇 설정 ===")
        logging.info(f"드랍 확률: {self.drop_rate*100}%")
        logging.info(f"일일 한도: {self.max_daily_amount} RBTC")
        logging.info(f"쿨타임: {self.cooldown_seconds}초")
        logging.info(f"RSK RPC: {self.base_rpc}")
        logging.info(f"봇 지갑: {self.bot_wallet_address[:10]}...{self.bot_wallet_address[-8:] if self.bot_wallet_address else 'None'}")
        logging.info(f"TX Manager: {'활성화' if self.tx_manager else '비활성화'}")
        logging.info(f"================")
    
    def get_today_key(self) -> str:
        """오전 9시 기준으로 오늘 날짜 키 반환"""
        now = datetime.now()
        if now.hour < 9:
            # 오전 9시 이전이면 전날로 계산
            return (now - timedelta(days=1)).date().isoformat()
        else:
            return now.date().isoformat()
    
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
• 1회 드랍량: 0.0000025 RBTC
• 일일 최대: {self.max_daily_amount:.8f} RBTC
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
                self.bot.reply_to(message, "❌ 유효하지 않은 지갑 주소입니다. RSK 체인 주소를 확인해주세요.")
        
        @self.bot.message_handler(commands=['wallet'])
        def handle_wallet_info(message):
            """내 지갑 정보 조회"""
            user_id = str(message.from_user.id)
            wallet = self.wallet_manager.get_wallet(user_id)
            
            if wallet:
                # RBTC 잔액 조회
                balance = 0.0
                if self.tx_manager:
                    balance = self.tx_manager.get_rbtc_balance(wallet)
                
                wallet_text = f"""
💳 내 지갑 정보

📍 주소: `{wallet}`
💰 잔액: {balance:.8f} RBTC
                """
                self.bot.reply_to(message, wallet_text, parse_mode='Markdown')
            else:
                self.bot.reply_to(message, "❌ 등록된 지갑이 없습니다. /set 명령어로 지갑을 등록해주세요.")
        
        @self.bot.message_handler(commands=['info'])
        def handle_info(message):
            """봇 정보 및 설정"""
            today = self.get_today_key()
            today_sent = self.daily_sent.get(today, 0)
            
            info_text = f"""
📊 봇 설정 정보:

🎲 드랍 확률: 비밀 🤫
💰 하루 최대: {self.max_daily_amount:.8f} RBTC
📈 오늘 전송: {today_sent:.8f} RBTC
👥 등록 지갑: {len(self.wallet_manager.get_all_wallets())}개
⏰ 전송 쿨타임: {int(self.cooldown_seconds)}초

🌐 체인: Rootstock Network
💳 봇 지갑: `{self.bot_wallet_address[:10]}...{self.bot_wallet_address[-8:]}`
            """
            self.bot.reply_to(message, info_text)
        
        @self.bot.message_handler(commands=['stats'])
        def handle_stats(message):
            """드랍 통계 (관리자 전용)"""
            # 관리자 확인
            if str(message.from_user.id) != self.admin_user_id:
                self.bot.reply_to(message, "❌ 관리자만 사용할 수 있는 명령어입니다.")
                return
            
            if not self.drop_history:
                self.bot.reply_to(message, "📊 아직 드랍 이력이 없습니다.")
                return
            
            # 통계 계산
            total_drops = len(self.drop_history)
            total_amount = sum(record['amount_rbtc'] for record in self.drop_history)
            
            # 사용자별 통계
            user_stats = {}
            for record in self.drop_history:
                user_id = record['telegram_id']
                username = record['telegram_username']
                if user_id not in user_stats:
                    user_stats[user_id] = {
                        'username': username,
                        'count': 0,
                        'total': 0,
                        'wallet': record['wallet_address']
                    }
                user_stats[user_id]['count'] += 1
                user_stats[user_id]['total'] += record['amount_rbtc']
            
            # 상위 10명
            top_users = sorted(user_stats.items(), key=lambda x: x[1]['total'], reverse=True)[:10]
            
            stats_text = f"""📊 드랍 통계
            
총 드랍 횟수: {total_drops}회
총 지급 RBTC: {total_amount:.8f}
총 참여자 수: {len(user_stats)}명

🏆 TOP 10 사용자:
"""
            for i, (user_id, stats) in enumerate(top_users, 1):
                stats_text += f"{i}. {stats['username']} - {stats['count']}회, {stats['total']:.8f} RBTC\n"
            
            self.bot.reply_to(message, stats_text)
        
        @self.bot.message_handler(commands=['blacklist'])
        def handle_blacklist(message):
            """블랙리스트 관리 (관리자 전용)"""
            # 관리자 확인
            if str(message.from_user.id) != self.admin_user_id:
                self.bot.reply_to(message, "❌ 관리자만 사용할 수 있는 명령어입니다.")
                return
            
            parts = message.text.split()
            if len(parts) < 2:
                help_text = """
🚫 블랙리스트 관리:

/blacklist add @username 또는 user_id - 추가
/blacklist remove @username 또는 user_id - 제거
/blacklist list - 목록 보기
                """
                self.bot.reply_to(message, help_text)
                return
            
            action = parts[1].lower()
            
            if action == 'list':
                if not self.blacklist:
                    self.bot.reply_to(message, "📋 블랙리스트가 비어있습니다.")
                else:
                    list_text = "🚫 블랙리스트:\n\n"
                    for user_id in self.blacklist:
                        list_text += f"• {user_id}\n"
                    self.bot.reply_to(message, list_text)
            
            elif action in ['add', 'remove'] and len(parts) >= 3:
                target = parts[2]
                
                # @username 형식 처리
                if target.startswith('@'):
                    self.bot.reply_to(message, "❌ 사용자 ID를 직접 입력해주세요. (예: 123456789)")
                    return
                
                # user_id 검증
                try:
                    user_id = str(int(target))  # 숫자인지 확인
                except:
                    self.bot.reply_to(message, "❌ 올바른 사용자 ID를 입력해주세요.")
                    return
                
                if action == 'add':
                    if user_id not in self.blacklist:
                        self.blacklist.append(user_id)
                        self.wallet_manager.save_blacklist(self.blacklist)
                        self.bot.reply_to(message, f"✅ {user_id}를 블랙리스트에 추가했습니다.")
                        logging.info(f"블랙리스트 추가: {user_id} by {message.from_user.id}")
                    else:
                        self.bot.reply_to(message, f"⚠️ {user_id}는 이미 블랙리스트에 있습니다.")
                
                elif action == 'remove':
                    if user_id in self.blacklist:
                        self.blacklist.remove(user_id)
                        self.wallet_manager.save_blacklist(self.blacklist)
                        self.bot.reply_to(message, f"✅ {user_id}를 블랙리스트에서 제거했습니다.")
                        logging.info(f"블랙리스트 제거: {user_id} by {message.from_user.id}")
                    else:
                        self.bot.reply_to(message, f"⚠️ {user_id}는 블랙리스트에 없습니다.")
            else:
                self.bot.reply_to(message, "❌ 잘못된 명령어 형식입니다. /blacklist 를 입력해 도움말을 확인하세요.")
        
        
        @self.bot.message_handler(content_types=['new_chat_members'])
        def handle_new_member(message):
            """봇이 새 그룹에 추가되었을 때"""
            for new_member in message.new_chat_members:
                if new_member.id == self.bot_info.id:
                    # 봇이 새 그룹에 추가됨
                    chat_title = message.chat.title or "Unknown"
                    chat_id = message.chat.id
                    inviter = f"@{message.from_user.username}" if message.from_user.username else message.from_user.first_name
                    
                    logging.info(f"🎉 봇이 새 그룹에 추가됨: {chat_title} (ID: {chat_id}) by {inviter}")
                    
                    # 관리자에게 알림 (ADMIN_USER_ID가 설정된 경우)
                    if self.admin_user_id:
                        try:
                            admin_msg = f"""🤖 봇이 새 그룹에 추가되었습니다!
                            
📍 그룹: {chat_title}
🆔 ID: {chat_id}
👤 초대자: {inviter}
🕐 시간: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"""
                            self.bot.send_message(self.admin_user_id, admin_msg)
                        except Exception as e:
                            logging.error(f"관리자 알림 실패: {e}")
                    
                    # 새 그룹에 환영 메시지
                    welcome_msg = """🎯 RSK RBTC 드랍 봇입니다!
                    
채팅하면 랜덤으로 RBTC를 드랍합니다.
먼저 개인 채팅에서 /set 명령어로 지갑을 등록하세요!"""
                    self.bot.send_message(chat_id, welcome_msg)
        
        @self.bot.message_handler(content_types=['left_chat_member'])
        def handle_left_member(message):
            """봇이 그룹에서 제거되었을 때"""
            if message.left_chat_member.id == self.bot_info.id:
                chat_title = message.chat.title or "Unknown"
                chat_id = message.chat.id
                
                logging.info(f"😢 봇이 그룹에서 제거됨: {chat_title} (ID: {chat_id})")
                
                # 관리자에게 알림
                if self.admin_user_id:
                    try:
                        admin_msg = f"""🤖 봇이 그룹에서 제거되었습니다.
                        
📍 그룹: {chat_title}
🆔 ID: {chat_id}
🕐 시간: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"""
                        self.bot.send_message(self.admin_user_id, admin_msg)
                    except:
                        pass
        
        @self.bot.message_handler(func=lambda message: True)
        def handle_all_messages(message):
            """모든 메시지 처리 - 랜덤 드랍 트리거"""
            logging.info("=== 메시지 핸들러 호출됨 ===")
            if message.from_user:
                user_id = str(message.from_user.id)
                user_name = f"@{message.from_user.username}" if message.from_user.username else message.from_user.first_name or "Unknown"
                
                # 메시지 수신 로깅
                logging.info(f"메시지 수신 - 채팅: {message.chat.title if hasattr(message.chat, 'title') else 'Private'}, 사용자: {user_name}")
                
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
        logging.info(f"드랍 처리 시작 - 사용자: {user_name} ({user_id})")
        
        # 블랙리스트 체크 (가장 먼저!)
        if user_id in self.blacklist:
            logging.info(f"블랙리스트 사용자: {user_name} ({user_id})")
            return  # 블랙리스트 사용자는 드랍 불가
        
        # 개인 채팅에서는 드랍 비활성화
        if message.chat.type == 'private':
            logging.info(f"개인 채팅에서는 드랍이 비활성화됨")
            return
        
        # [modify] 메시지 길이 체크 (5글자 이상)
        if not message.text or len(message.text) < 5:
            logging.info(f"메시지 길이 부족: {len(message.text) if message.text else 0}글자 (최소 5글자)")
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
        
        # 채팅방 인원 체크 (3명 이하면 드랍 금지)
        chat_id = message.chat.id
        chat_member_count = 4  # 기본값 (멤버 수를 가져올 수 없을 때)
        try:
            chat_member_count = self.bot.get_chat_member_count(chat_id)
            if chat_member_count <= 3:
                logging.info(f"채팅방 인원 부족: {chat_member_count}명 (최소 4명 필요)")
                return  # 3명 이하면 드랍 안함
        except:
            # 멤버 수를 가져올 수 없으면 기본값(4) 사용
            logging.debug(f"채팅방 멤버 수 조회 실패, 기본값 사용: {chat_member_count}")
            pass
        
        # 연속 당첨 방지 체크
        if not self.last_winner_tracker.can_receive_drop(chat_id, user_id, total_users=chat_member_count):
            logging.info(f"연속 당첨 방지: {user_name} ({user_id})는 마지막 당첨자")
            return  # 마지막 당첨자는 못 받음
        
        # 일일 한도 확인 (오전 9시 기준)
        today = self.get_today_key()
        today_sent = self.daily_sent.get(today, 0)
        
        if today_sent >= self.max_daily_amount:
            # 오늘 처음으로 한도 도달시에만 알림 (채팅방별로)
            today_notifications = self.limit_notifications.get(today, [])
            
            if chat_id not in today_notifications:
                # 이 채팅방에 오늘 알림을 보낸 적이 없음
                limit_msg = "💸 오늘의 RBTC 드랍이 모두 소진되었습니다!\n내일 다시 찾아주세요~ 🌙"
                self.bot.send_message(chat_id, limit_msg)
                
                # 알림 기록 저장
                today_notifications.append(chat_id)
                self.limit_notifications[today] = today_notifications
                self.wallet_manager.save_limit_notifications(self.limit_notifications)
                
                logging.info(f"일일 한도 도달 알림: {today_sent:.8f}/{self.max_daily_amount:.8f} RBTC (채팅방: {chat_id})")
            return  # 일일 한도 초과
        
        # 랜덤 드랍 여부 결정
        if not self.tx_manager:
            logging.error("TransactionManager가 초기화되지 않았습니다. PRIVATE_KEY를 확인하세요.")
            return
        
        if not self.tx_manager.should_drop(self.drop_rate):
            # 20% 확률이므로 5번 중 1번만 당첨
            return  # 드랍 안함
        
        logging.info(f"🎉 드랍 당첨! 사용자: {user_name}, 지갑: {wallet_address[:10]}...")
        
        # 드랍 금액 (가스비 고려한 적정 금액)
        drop_amount = 0.0000025  # 고정 금액: 0.0000025 RBTC (~400원)
        
        # 일일 한도 체크
        if today_sent + drop_amount > self.max_daily_amount:
            drop_amount = self.max_daily_amount - today_sent
            if drop_amount < 0.00000001:
                return  # 너무 적으면 드랍 안함
        
        # RBTC 전송 (최대 5회 재시도)
        max_retries = 5
        tx_hash = None
        
        for attempt in range(max_retries):
            tx_hash = self.tx_manager.send_rbtc(
                wallet_address, 
                drop_amount
            )
            
            if tx_hash:
                break
            else:
                logging.warning(f"드랍 전송 실패 (시도 {attempt + 1}/{max_retries}): {user_name}")
                if attempt < max_retries - 1:
                    import time
                    time.sleep(2)  # 2초 대기 후 재시도
        
        if tx_hash:
            # 일일 전송량 업데이트 및 저장
            self.daily_sent[today] = today_sent + drop_amount
            self.wallet_manager.save_daily_sent(self.daily_sent)
            
            # [modify] 쿨타임 업데이트 (새로 추가)
            self.last_transaction_time[user_id] = datetime.now()  # [modify] 현재 시간으로 업데이트
            
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
            
            # 라운드 로빈 업데이트
            self.last_winner_tracker.update_winner(chat_id, user_id)
            self.wallet_manager.save_last_winners(self.last_winner_tracker.save_to_dict())
            
            # 드랍 이력 기록
            drop_record = {
                "wallet_address": wallet_address,
                "amount_rbtc": drop_amount,
                "timestamp": datetime.now().strftime('%Y-%m-%d %H:%M:%S KST'),
                "telegram_id": user_id,
                "telegram_username": user_name,
                "tx_hash": tx_hash,
                "chat_id": chat_id
            }
            self.drop_history.append(drop_record)
            self.wallet_manager.save_drop_history(self.drop_history)
        else:
            # 모든 재시도 실패시 로그만 남김
            logging.error(f"드랍 전송 완전 실패: {user_name} ({user_id}) - 모든 재시도 소진")
    
    def run(self):
        """봇 실행"""
        import uuid
        instance_id = str(uuid.uuid4())[:8]
        logging.info(f"RBTC 드랍 봇 시작 - Instance: {instance_id}")
        logging.info(f"드랍 확률: {self.drop_rate*100:.1f}%, 일일 한도: {self.max_daily_amount:.8f} RBTC")
        
        # 초기 대기 (이전 인스턴스 종료 대기)
        logging.info("초기화 대기 중...")
        time.sleep(3)
        
        retry_count = 0
        while retry_count < 10:
            try:
                logging.info(f"봇 폴링 시작... (시도: {retry_count + 1})")
                self.bot.infinity_polling(timeout=10, long_polling_timeout=5, skip_pending=True)
                break  # 정상 종료시 루프 탈출
            except Exception as e:
                retry_count += 1
                logging.error(f"봇 실행 오류 (시도 {retry_count}/10): {e}")
                if retry_count < 10:
                    wait_time = min(retry_count * 5, 30)  # 최대 30초까지 대기
                    logging.info(f"{wait_time}초 후 재시작...")
                    time.sleep(wait_time)
                else:
                    logging.error("최대 재시도 횟수 초과. 봇 종료.")
                    break
        
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