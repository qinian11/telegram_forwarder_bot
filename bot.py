import logging
import asyncio
import json
import time
from telegram import Update, InputMediaPhoto, InputMediaVideo
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes
)

# ========== 加载配置 ==========
try:
    with open("config.json", "r", encoding="utf-8") as f:
        config = json.load(f)
    BOT_TOKEN = config["bot_token"]
    TARGET_CHANNEL = config["target_channel"]
    REMOVE_KEYWORDS = config["remove_keywords"]
except (FileNotFoundError, KeyError, json.JSONDecodeError) as e:
    print("❌ 配置文件加载失败:", e)
    exit(1)

# ========== 日志配置 ==========
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

# ========== 缓存媒体组 ==========
media_group_cache = {}

# ========== 工具函数 ==========
def clean_caption(text: str) -> str:
    for word in REMOVE_KEYWORDS:
        text = text.replace(word, "")
    return text.strip()

# ========== 命令处理 ==========
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🤖 请直接发送内容（文字/图片/视频），我会自动整理后转发到频道。")

# ========== 媒体组处理 ==========
async def process_media_group(media_group_id: str, context: ContextTypes.DEFAULT_TYPE):
    max_retries = 3
    retry_delay = 2

    for attempt in range(max_retries):
        try:
            await asyncio.sleep(3 + attempt)

            if media_group_id not in media_group_cache:
                logger.warning(f"媒体组 {media_group_id} 已过期或不存在")
                return

            messages, collected_text = media_group_cache.pop(media_group_id)

            messages.sort(key=lambda msg: msg.message_id)

            full_text = "\n".join(filter(None, [collected_text]))
            cleaned_text = clean_caption(full_text)

            media_list = []
            for idx, msg in enumerate(messages):
                caption = cleaned_text if idx == 0 else None

                if msg.photo:
                    media_list.append(InputMediaPhoto(media=msg.photo[-1].file_id, caption=caption))
                elif msg.video:
                    media_list.append(InputMediaVideo(media=msg.video.file_id, caption=caption))

            logger.info(f"准备发送媒体组 {media_group_id} 包含 {len(media_list)} 个媒体")

            await context.bot.send_media_group(
                chat_id=TARGET_CHANNEL,
                media=media_list,
                write_timeout=30
            )
            await messages[0].reply_text("✅ 媒体组已整理转发到频道")
            return

        except Exception as e:
            if attempt < max_retries - 1:
                logger.warning(f"媒体组 {media_group_id} 第 {attempt + 1} 次重试...")
                await asyncio.sleep(retry_delay)
                continue
            logger.error(f"媒体组转发失败（{media_group_id}）: {str(e)}", exc_info=True)
            await messages[0].reply_text("❌ 转发失败，请尝试重新发送")

# ========== 消息转发 ==========
async def forward_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message
    if update.effective_chat.type != "private":
        return

    try:
        # 处理媒体组
        if msg.media_group_id:
            group_id = str(msg.media_group_id)
            text_content = ""
            if msg.caption:
                text_content += msg.caption + "\n"
            if msg.text:
                text_content += msg.text + "\n"

            if group_id not in media_group_cache:
                media_group_cache[group_id] = ([msg], text_content.strip())
                asyncio.create_task(process_media_group(group_id, context))
            else:
                media_group_cache[group_id][0].append(msg)
                media_group_cache[group_id] = (
                    media_group_cache[group_id][0],
                    media_group_cache[group_id][1] + "\n" + text_content.strip()
                )
            return

        # 处理单条消息
        if msg.text or msg.caption:
            cleaned_text = clean_caption(msg.text or msg.caption)
            await context.bot.send_message(chat_id=TARGET_CHANNEL, text=cleaned_text)
            await msg.reply_text("✅ 文本已转发到频道")
        elif msg.photo:
            await context.bot.send_photo(
                chat_id=TARGET_CHANNEL,
                photo=msg.photo[-1].file_id,
                caption=clean_caption(msg.caption or "")
            )
            await msg.reply_text("✅ 图片已转发到频道")
        elif msg.video:
            await context.bot.send_video(
                chat_id=TARGET_CHANNEL,
                video=msg.video.file_id,
                caption=clean_caption(msg.caption or "")
            )
            await msg.reply_text("✅ 视频已转发到频道")

    except Exception as e:
        logger.error(f"转发失败: {e}")
        await msg.reply_text("❌ 转发失败，请检查内容格式")

# ========== 启动机器人 ==========
def run_bot():
    app = ApplicationBuilder().token(BOT_TOKEN).connect_timeout(30).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.ALL & ~filters.COMMAND, forward_message))

    logger.info(f"服务器启动时间: {time.strftime('%Y-%m-%d %H:%M:%S')}")
    app.run_polling(poll_interval=1, timeout=30, drop_pending_updates=True)

if __name__ == "__main__":
    run_bot()
