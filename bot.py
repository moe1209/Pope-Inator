import os
import logging
import requests
import asyncio
from telegram import Bot
from telegram.ext import Updater, CommandHandler
from web3 import Web3

# Logging setup
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# Access environment variables
TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
WALLET_ADDRESS = os.environ.get("YOUR_WALLET")
PRIVATE_KEY = os.environ.get("PRIVATE_KEY")
WEB3_PROVIDER = os.environ.get("WEB3_PROVIDER")

# Validate environment variables
if not all([TOKEN, WALLET_ADDRESS, PRIVATE_KEY, WEB3_PROVIDER]):
    raise Exception("Missing required environment variables")

# Web3 Setup
w3 = Web3(Web3.HTTPProvider(WEB3_PROVIDER))
if not w3.is_connected():
    raise Exception("Failed to connect to blockchain")

# Initialize Telegram bot
updater = Updater(token=TOKEN, use_context=True)
dispatcher = updater.dispatcher

# Whale detection settings
WHALE_THRESHOLD = 100000  # $100,000
WHALE_WALLETS = set()  # Dynamic list of whale wallets

# Notification settings
NOTIFICATIONS_ENABLED = True

# Rate limiting settings
RATE_LIMIT = 5  # Max 5 commands per minute per user
user_command_count = {}

# **Rate Limiting Decorator**
def rate_limit(func):
    @wraps(func)
    def wrapped(update, context):
        user_id = update.message.from_user.id
        if user_id not in user_command_count:
            user_command_count[user_id] = 0

        if user_command_count[user_id] >= RATE_LIMIT:
            update.message.reply_text("🚫 Rate limit exceeded. Please try again later.")
            return

        user_command_count[user_id] += 1
        return func(update, context)
    return wrapped

# **Fetch Current Price**
def get_current_price(token_address):
    url = f"https://api.coingecko.com/api/v3/simple/token_price/binance-smart-chain?contract_addresses={token_address}&vs_currencies=usd"
    try:
        response = requests.get(url)
        response.raise_for_status()
        data = response.json()
        return data.get(token_address.lower(), {}).get("usd", 0.0)  # Prevent KeyError
    except requests.RequestException as e:
        logger.error(f"Error fetching price data: {e}")
        return None

# **AI Whale Detection**
async def detect_whales():
    while True:
        try:
            # Fetch the latest block
            latest_block = w3.eth.get_block('latest', full_transactions=True)
            for tx in latest_block.transactions:
                value = w3.fromWei(tx["value"], 'ether')
                token_address = tx["to"]
                price = get_current_price(token_address)

                if price is None:
                    continue  # Skip if price data is unavailable

                usd_value = value * price

                # Check if the transaction exceeds the whale threshold
                if usd_value >= WHALE_THRESHOLD:
                    whale_wallet = tx["from"]
                    if whale_wallet not in WHALE_WALLETS:
                        WHALE_WALLETS.add(whale_wallet)
                        logger.info(f"🚨 New Whale Detected: {whale_wallet}")
                        # Notify the user
                        if NOTIFICATIONS_ENABLED:
                            updater.bot.send_message(
                                chat_id=updater.dispatcher.chat_data.get("chat_id"),
                                text=f"🚨 New Whale Detected: {whale_wallet}"
                            )
            await asyncio.sleep(10)  # Async sleep instead of blocking
        except Exception as e:
            logger.error(f"Error detecting whales: {e}")
            await asyncio.sleep(10)

# **Buy Meme Coin**
@rate_limit
def buy_meme_coin(update, context):
    token_address = context.args[0]  # Get token address from command
    amount = w3.toWei(0.1, 'ether')  # 0.1 BNB buy

    try:
        nonce = w3.eth.get_transaction_count(WALLET_ADDRESS)
        tx = {
            'nonce': nonce,
            'to': token_address,
            'value': amount,
            'gas': 200000,
            'gasPrice': w3.toWei('5', 'gwei'),
            'chainId': 56  # BSC
        }

        signed_tx = w3.eth.account.sign_transaction(tx, PRIVATE_KEY)
        tx_hash = w3.eth.send_raw_transaction(signed_tx.rawTransaction)
        update.message.reply_text(f"✅ Bought Meme Coin: {tx_hash.hex()}")
    except Exception as e:
        logger.error(f"Error executing buy transaction: {e}")
        update.message.reply_text(f"❌ Failed to execute trade: {e}")

# **List Detected Whales**
@rate_limit
def list_whales(update, context):
    if WHALE_WALLETS:
        update.message.reply_text(f"🐋 Monitored Whales:\n{', '.join(WHALE_WALLETS)}")
    else:
        update.message.reply_text("No whales detected yet.")

# **Toggle Notifications**
@rate_limit
def toggle_notifications(update, context):
    global NOTIFICATIONS_ENABLED
    NOTIFICATIONS_ENABLED = not NOTIFICATIONS_ENABLED
    status = "enabled" if NOTIFICATIONS_ENABLED else "disabled"
    update.message.reply_text(f"🔔 Notifications {status}.")

# **Start Command**
@rate_limit
def start(update, context):
    update.message.reply_text("🚀 Whale Bot Started! Use /help to see available commands.")

# **Help Command**
@rate_limit
def help(update, context):
    update.message.reply_text(
        "🤖 Available Commands:\n"
        "/start - Start the bot\n"
        "/trade <token_address> - Buy a meme coin\n"
        "/whales - List detected whales\n"
        "/notify - Toggle notifications\n"
        "/help - Show this help message"
    )

# Add handlers
dispatcher.add_handler(CommandHandler("start", start))
dispatcher.add_handler(CommandHandler("help", help))
dispatcher.add_handler(CommandHandler("trade", buy_meme_coin))
dispatcher.add_handler(CommandHandler("whales", list_whales))
dispatcher.add_handler(CommandHandler("notify", toggle_notifications))

# Start whale monitoring in a separate thread
whale_thread = threading.Thread(target=detect_whales)
whale_thread.daemon = True
whale_thread.start()

# Start bot
def start_bot():
    updater.start_polling()
    updater.idle()

if __name__ == "__main__":
    start_bot()