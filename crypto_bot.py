import asyncio
import logging
import time

from pycoingecko import CoinGeckoAPI
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

# CONFIG
BOT_TOKEN = "8587733738:AAEZwJz50jL5nutbhm5u6dzzS7vjVkZKSKk"           # ← Paste from @BotFather
YOUR_CHAT_ID = 1973535887                 # ← Your Telegram user ID (from @userinfobot)

COINS_TO_SCAN = [
    "bitcoin", "ethereum", "solana", "dogecoin", "cardano",
    "ripple", "binancecoin", "avalanche-2", "polkadot", "chainlink"
]  # Add more CoinGecko IDs if you want

SCAN_INTERVAL_SEC = 180                     # 3 minutes
PRICE_CHANGE_THRESHOLD = 5.0                # %
VOLUME_CHANGE_THRESHOLD = 25.0              # %
FIB_LEVELS = [1.618, 2.618, 4.236]

cg = CoinGeckoAPI()
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

watchlist = {}  # coin_id → dict with entry_price, etc.

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🚀 Crypto Scanner Bot started!\n\n"
        "Scanning for pumps/dumps. Alerts to you.\n"
        "Commands: /watchlist /status"
    )

async def watchlist_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not watchlist:
        await update.message.reply_text("Watchlist empty.")
        return
    prices = cg.get_price(ids=",".join(watchlist.keys()), vs_currencies="usd")
    msg = "Watchlist:\n\n"
    for coin, d in watchlist.items():
        curr = prices.get(coin, {}).get("usd", 0)
        if curr == 0: continue
        perc = ((curr - d["entry_price"]) / d["entry_price"]) * 100
        msg += f"• {coin.upper()}: {perc:+.1f}% ({d['direction']}) from ${d['entry_price']:.2f}\n"
    await update.message.reply_text(msg)

async def status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = f"Scanning {len(COINS_TO_SCAN)} coins every {SCAN_INTERVAL_SEC}s\nThreshold: ±{PRICE_CHANGE_THRESHOLD}% price + {VOLUME_CHANGE_THRESHOLD}% vol"
    await update.message.reply_text(msg)

async def scanner(context: ContextTypes.DEFAULT_TYPE):
    for coin_id in COINS_TO_SCAN:
        try:
            chart = cg.get_coin_market_chart_by_id(coin_id, "usd", days=1, interval="minute")
            if not chart or "prices" not in chart or len(chart["prices"]) < 5:
                continue
            prices = chart["prices"]
            volumes = chart["total_volumes"]
            now_price = prices[-1][1]
            now_vol = volumes[-1][1]
            past_idx = max(0, len(prices) - 4)
            past_price = prices[past_idx][1]
            past_vol = volumes[past_idx][1]
            p_change = ((now_price - past_price) / past_price) * 100
            v_change = ((now_vol - past_vol) / past_vol) * 100 if past_vol > 0 else 0
            direction = "pump" if p_change > 0 else "dump"
            abs_p = abs(p_change)
            link = f"https://www.coingecko.com/en/coins/{coin_id}"
            if abs_p >= PRICE_CHANGE_THRESHOLD and v_change >= VOLUME_CHANGE_THRESHOLD:
                if coin_id not in watchlist:
                    watchlist[coin_id] = {
                        "entry_price": past_price,
                        "entry_time": int(prices[-1][0] / 1000),
                        "last_alerted_perc": abs_p,
                        "direction": direction
                    }
                    await context.bot.send_message(
                        YOUR_CHAT_ID,
                        f"{'🚀' if direction=='pump' else '📉'} {coin_id.upper()} {direction}!\n"
                        f"{p_change:+.1f}% price, +{v_change:.0f}% vol\n"
                        f"Entry ${past_price:,.2f} → Now ${now_price:,.2f}\n{link}"
                    )
                else:
                    entry = watchlist[coin_id]["entry_price"]
                    total_p = ((now_price - entry) / entry) * 100
                    last = watchlist[coin_id]["last_alerted_perc"]
                    if abs(total_p) > last + PRICE_CHANGE_THRESHOLD:
                        watchlist[coin_id]["last_alerted_perc"] = abs(total_p)
                        await context.bot.send_message(
                            YOUR_CHAT_ID,
                            f"📈 Further {direction} on {coin_id.upper()}: {total_p:+.1f}% total\n${now_price:,.2f}\n{link}"
                        )
                    if direction == "pump":
                        for fib in FIB_LEVELS:
                            fib_price = entry * fib
                            if now_price >= fib_price and fib_price > entry * (1 + last / 100):
                                await context.bot.send_message(
                                    YOUR_CHAT_ID,
                                    f"🎯 {coin_id.upper()} Fib {fib}x hit!\nTotal +{(fib-1)*100:.1f}%\n${now_price:,.2f}\n{link}"
                                )
        except Exception as e:
            logger.warning(f"Scan error {coin_id}: {e}")

def main():
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("watchlist", watchlist_cmd))
    app.add_handler(CommandHandler("status", status))
    app.job_queue.run_repeating(scanner, interval=SCAN_INTERVAL_SEC, first=10)
    print("Bot starting...")
    app.run_polling()

if __name__ == "__main__":
    main()
