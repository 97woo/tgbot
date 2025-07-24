# RSK RBTC Drop Telegram Bot

A Telegram bot that randomly drops RBTC (RSK Bitcoin) to registered users on the RSK/Rootstock network.

## Features

- 🎯 **Wallet Registration**: Users can register their RSK wallet address
- 🎲 **Random Drops**: Configurable chance to receive RBTC when chatting
- ⏰ **Cooldown System**: Prevents spam with configurable cooldown periods
- 💰 **Daily Limits**: Set maximum daily RBTC distribution
- 🔒 **Security**: Input validation and secure transaction handling
- ⚡ **Gas Optimization**: Dynamic gas estimation for RSK network

## Commands

- `/start` - Welcome message and bot introduction
- `/set wallet_address` - Register your RSK wallet address
- `/wallet` - View your registered wallet
- `/info` - Display bot configuration and statistics

## Setup

1. Clone the repository:
```bash
git clone https://github.com/bennjung/tgbot.git
cd tgbot
```

2. Install dependencies:
```bash
pip install -r requirements.txt
```

3. Configure environment variables:
```bash
cp .env.example .env
# Edit .env with your configuration
```

4. Run the bot:
```bash
python rbtc_bot.py
```

## Configuration

See `.env.example` for all configuration options:

- `TELEGRAM_BOT_TOKEN` - Your Telegram bot token from @BotFather
- `RPC_URL` - RSK RPC endpoint (testnet/mainnet)
- `PRIVATE_KEY` - Bot wallet private key (holds RBTC for drops)
- `DROP_RATE` - Probability of drop per message (0.05 = 5%)
- `MAX_DAILY_AMOUNT` - Maximum RBTC to distribute per day (0.00003125 = ~5000 KRW)
- `COOLDOWN_SECONDS` - Cooldown between drops per user

## RSK Network Details

- **Mainnet RPC**: https://public-node.rsk.co
- **Testnet RPC**: https://public-node.testnet.rsk.co
- **Chain ID**: 30 (mainnet), 31 (testnet)
- **Block Time**: ~5 seconds
- **RBTC Decimals**: 18 (same as ETH)

## Security Considerations

- Never commit your `.env` file
- Use small drop amounts due to RBTC's high value
- Test thoroughly on testnet first
- Monitor bot wallet balance
- Implement proper access controls

## Gas Analysis Tools

The repository includes tools for analyzing gas usage:
- `gas_analysis.py` - Detailed gas analysis with pandas
- `simple_gas_analysis.py` - Basic analysis without dependencies
- `usdc_txs.csv` - Sample transaction data

## License

This project is open source. Feel free to fork and modify.
