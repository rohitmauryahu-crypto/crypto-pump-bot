import asyncio
import logging
import time

from pycoingecko import CoinGeckoAPI
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

# ────────────────────────────────────────────────
#               CONFIGURATION
# ────────────────────────────────────────────────

BOT_TOKEN = "8587733738:AAEZwJz50jL5nutbhm5u6dzzS7vjVkZKSKk"  # Your new bot token
YOUR_CHAT_ID = 1973535887                                     # ← REPLACE WITH YOUR REAL TELEGRAM ID (from @userinfobot)

COINS_TO_SCAN = [
    "bitcoin", "ethereum", "solana", "dogecoin", "cardano",
    "ripple", "binancecoin", "avalanche-2", "polkadot", "chainlink"
]  # CoinGecko IDs – add more if you want

SCAN_INTERVAL_SEC = 180                     # Check every 3 minutes
PRICE_CHANGE_THRESHOLD = 5.0                # % price change to trigger
VOLUME_CHANGE_THRESHOLD = 25.0              # % volume spike required
FIB_LEVELS = [1.618, 2.618, 4.236]          # Fibonacci extensions for pumps

cg = CoinGeckoAPI()
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

watchlist = {}  # coin_id → {"entry_price": float, "entry_time": int, "last_alerted_perc": float, "direction": str}

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🚀 Crypto Pump/Dump Scanner Bot started!\n\n"
        "Scanning popular coins every few minutes for ±5% moves with volume spike.\n"
        "Alerts go directly to you.\n\n"
        "Commands:\n"
        "/watchlist   – show current watched coins\n"
        "/status      – show settings"
    )

async def watchlist_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not watchlist:
        await update.message.reply_text("Watchlist is empty right now.")
        return

    prices = cg.get_price(ids=",".join(watchlist.keys()), vs_currencies="usd")
    msg = "📋 Current Watchlist:\n\n"

    for coin, data in watchlist.items():
        curr_price = prices.get(coin, {}).get("usd", 0)
        if curr_price == 0:
            continue
        perc_from_entry = ((curr_price - data["entry_price"]) / data["entry_price"]) * 100
        msg += (
            f"• {coin.upper()}\n"
            f"  Direction: {data['direction'].upper()}\n"
            f"  Entry: ${data['entry_price']:,.2f}\n"
            f"  Current: ${curr_price:,.2f} ({perc_from_entry:+.1f}%)\n"
            f"  https://www.coingecko.com/en/coins/{coin}\n\n"
        )

    await update.message.reply_text(msg)

async def status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = (
        f"Status:\n"
        f"• Scanning {len(COINS_TO_SCAN)} coins\n"
        f"• Interval: every {SCAN_INTERVAL_SEC} seconds\n"
        f"• Price threshold: ±{PRICE_CHANGE_THRESHOLD}%\n"
        f"• Volume spike required: +{VOLUME_CHANGE_THRESHOLD}%\n"
        f"• Fib levels: {', '.join(str(x) for x in FIB_LEVELS)}\n"
        f"• Watchlist size: {len(watchlist)}"
    )
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
            now_vol   = volumes[-1][1]

            past_idx = max(0, len(prices) - 4)
            past_price = prices[past_idx][1]
            past_vol   = volumes[past_idx][1]

            price_change_pct = ((now_price - past_price) / past_price) * 100
            volume_change_pct = ((now_vol - past_vol) / past_vol) * 100 if past_vol > 0 else 0

            direction = "pump" if price_change_pct > 0 else "dump"
            abs_price_change = abs(price_change_pct)

            coingecko_link = f"https://www.coingecko.com/en/coins/{coin_id}"

            if abs_price_change >= PRICE_CHANGE_THRESHOLD and volume_change_pct >= VOLUME_CHANGE_THRESHOLD:
                if coin_id not in watchlist:
                    watchlist[coin_id] = {
                        "entry_price": past_price,
                        "entry_time": int(prices[-1][0] / 1000),
                        "last_alerted_perc": abs_price_change,
                        "direction": direction
                    }
                    await context.bot.send_message(
                        chat_id=YOUR_CHAT_ID,
                        text=(
                            f"{'🚀' if direction == 'pump' else '📉'} {coin_id.upper()} {direction.upper()} DETECTED!\n"
                            f"Price change: {price_change_pct:+.1f}% in ~15–20 min\n"
                            f"Volume spike: +{volume_change_pct:.0f}%\n"
                            f"Entry price: ${past_price:,.2f}\n"
                            f"Current: ${now_price:,.2f}\n"
                            f"{coingecko_link}"
                        ),
                        disable_web_page_preview=True
                    )
                else:
                    entry = watchlist[coin_id]["entry_price"]
                    total_change_pct = ((now_price - entry) / entry) * 100
                    last_alerted = watchlist[coin_id]["last_alerted_perc"]

                    if abs(total_change_pct) > last_alerted + PRICE_CHANGE_THRESHOLD:
                        watchlist[coin_id]["last_alerted_perc"] = abs(total_change_pct)
                        await context.bot.send_message(
                            chat_id=YOUR_CHAT_ID,
                            text=(
                                f"📈 Further {direction} on {coin_id.upper()}\n"
                                f"Total change: {total_change_pct:+.1f}% from entry\n"
                                f"Current price: ${now_price:,.2f}\n"
                                f"{coingecko_link}"
                            )
                        )

                    if direction == "pump":
                        for level in FIB_LEVELS:
                            fib_target = entry * level
                            if now_price >= fib_target and fib_target > entry * (1 + last_alerted / 100):
                                await context.bot.send_message(
                                    chat_id=YOUR_CHAT_ID,
                                    text=(
                                        f"🎯 {coin_id.upper()} hit Fib {level}x extension!\n"
                                        f"Total pump from entry: +{(level - 1) * 100:.1f}%\n"
                                        f"Current: ${now_price:,.2f}\n"
                                        f"{coingecko_link}"
                                    )
                                )

        except Exception as e:
            logger.warning(f"Error scanning {coin_id}: {e}")
            await asyncio.sleep(3)

def main():
    # IMPORTANT: Enable job_queue here to fix the NoneType crash
    app = Application.builder().token(BOT_TOKEN).job_queue(True).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("watchlist", watchlist_cmd))
    app.add_handler(CommandHandler("status", status))

    # Background scanner job
    app.job_queue.run_repeating(scanner, interval=SCAN_INTERVAL_SEC, first=10)

    print("Bot starting...")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
