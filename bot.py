"""
合併版 Telegram Bot
========================================
功能 1: 社群連結修復 (FixTweet 開源移植整合版)
    支援: X(Twitter)、Threads(脆)、Instagram、TikTok
    將原始連結轉換成可在 Telegram 正常顯示預覽的鏡像連結

功能 2: Pixiv 圖片搜尋(訊息內按鈕選單版)
    使用方式: 對Bot輸入 /start -> 點擊訊息裡的「🔍 搜尋圖片」按鈕
            -> 該則訊息就地切換成「請輸入關鍵詞」-> 直接打字傳送(不需要打指令)
            -> 跳出按鈕面板,先選「張數」再選「分級」,選完才開始搜尋

    分級規則(防護機制,非完全無限制):
    - 私訊裡:
        - 需先用 /confirm18 完成一次性成年聲明,才會顯示R-18/全部選項
    - 群組裡:
        - 預設只能選「全年齡」
        - 群組管理員可用 /enable18 為「這個群組」開啟R-18選項(一次設定,之後該群組成員搜圖都不用再驗證)
        - 管理員也可用 /disable18 隨時關閉

事前準備:
1. Telegram搜尋 @BotFather,輸入 /newbot 取得Token,存進 token.env
2. pip install gppt;gppt login(用Pixiv帳號登入一次,取得refresh_token存進 token.env)
3. pip install -r requirements.txt
   (需要: python-telegram-bot, python-dotenv, pixivpy3, requests)
4. python bot.py

========================================
架構說明(重要):
原本兩支程式分別用 telebot(同步)跟 telegram.ext(非同步)兩種不同函式庫。
這裡統一改寫成 telegram.ext(async),原因:
- python-telegram-bot 是目前主流且持續維護的函式庫
- Pixiv 搜圖牽涉到下載圖片、呼叫外部 API 等耗時 I/O,
  async 架構搭配 asyncio.to_thread 可以避免卡住整支 bot 對其他訊息的回應,
  且不需要像原本那樣手動開 threading.Thread 來繞過同步阻塞問題
========================================
"""

import os
import re
import json
import random
import asyncio
import requests
from dotenv import load_dotenv
from pixivpy3 import AppPixivAPI

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ChatType
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters,
)

# ============================================================
# 讀取 Token / 設定
# ============================================================
load_dotenv(dotenv_path="token.env")

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
PIXIV_REFRESH_TOKEN = os.getenv("PIXIV_REFRESH_TOKEN")

if not BOT_TOKEN:
    raise ValueError("❌ 錯誤：在 token.env 中找不到 TELEGRAM_BOT_TOKEN，請檢查檔案內容！")
if not PIXIV_REFRESH_TOKEN:
    raise ValueError("❌ 錯誤：在 token.env 中找不到 PIXIV_REFRESH_TOKEN，請先用 `gppt login` 取得token並寫入 token.env")

# ---- Pixiv API 初始化 ----
pixiv_api = AppPixivAPI()
pixiv_api.auth(refresh_token=PIXIV_REFRESH_TOKEN)


# ============================================================
# 功能 1：社群連結修復 (FixTweet 開源移植整合版)
# ============================================================

TWITTER_REGEX = r'(https?://(?:www\.)?(?:twitter\.com|x\.com)/[a-zA-Z0-9_]+/status/\d+)'
THREADS_REGEX = r'(https?://(?:www\.)?threads\.net/(?:@[a-zA-Z0-9_\.]+)/post/[a-zA-Z0-9_\-]+)'
INSTAGRAM_REGEX = r'(https?://(?:www\.)?instagram\.com/(?:p|reel)/[a-zA-Z0-9_\-]+)'
TIKTOK_REGEX = r'(https?://(?:www\.)?(?:vt\.tiktok\.com|tiktok\.com)/[a-zA-Z0-9_/]+)'


async def fix_social_links(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """偵測訊息中的社群連結，轉換成預覽鏡像連結並回覆"""
    if not update.message or not update.message.text:
        return

    user_message = update.message.text
    fixed_urls = []

    # 1. 處理 Twitter / X 網址
    twitter_matches = re.findall(TWITTER_REGEX, user_message)
    for match in twitter_matches:
        fixed = re.sub(r'https?://(?:www\.)?(?:twitter\.com|x\.com)', 'https://fxtwitter.com', match)
        fixed_urls.append(f"🐦 <b>Twitter / X 預覽：</b>\n{fixed}")

    # 2. 處理 Threads 脆 網址
    threads_matches = re.findall(THREADS_REGEX, user_message)
    for match in threads_matches:
        fixed = re.sub(r'https?://(?:www\.)?threads\.net', 'https://fxthreads.com', match)
        fixed_urls.append(f"🧵 <b>Threads 脆 預覽：</b>\n{fixed}")

    # 3. 處理 Instagram 網址 (開源項目內建使用 ddinstagram)
    instagram_matches = re.findall(INSTAGRAM_REGEX, user_message)
    for match in instagram_matches:
        fixed = re.sub(r'https?://(?:www\.)?instagram\.com', 'https://ddinstagram.com', match)
        fixed_urls.append(f"📸 <b>Instagram 預覽：</b>\n{fixed}")

    # 4. 處理 TikTok 抖音網址 (開源項目額外支援的 vxtiktok)
    tiktok_matches = re.findall(TIKTOK_REGEX, user_message)
    for match in tiktok_matches:
        fixed = re.sub(r'https?://(?:www\.)?(?:vt\.tiktok\.com|tiktok\.com)', 'https://vxtiktok.com', match)
        fixed_urls.append(f"🎵 <b>TikTok 預覽：</b>\n{fixed}")

    if fixed_urls:
        response_text = "\n\n".join(fixed_urls)
        await update.message.reply_text(text=response_text, parse_mode="HTML")


# ============================================================
# 功能 2：Pixiv 圖片搜尋
# ============================================================

# x_restrict 對照表(Pixiv官方分級欄位):0=全年齡 1=R-18 2=R-18G
RESTRICT_LABEL = {0: "全年齡", 1: "R-18", 2: "R-18G"}

COUNT_OPTIONS = [1, 3, 5, 10]
SEARCH_BUTTON_TEXT = "🔍 搜尋圖片"

DATA_FILE = "bot_data.json"


def _load_data() -> dict:
    if os.path.exists(DATA_FILE):
        try:
            with open(DATA_FILE, "r", encoding="utf-8") as f:
                raw = json.load(f)
                return {
                    "confirmed_adults": set(raw.get("confirmed_adults", [])),
                    "r18_enabled_groups": set(raw.get("r18_enabled_groups", [])),
                }
        except Exception as e:
            print(f"[警告] 讀取 {DATA_FILE} 失敗,將使用空白設定: {e}")
    return {"confirmed_adults": set(), "r18_enabled_groups": set()}


def _save_data():
    try:
        with open(DATA_FILE, "w", encoding="utf-8") as f:
            json.dump(
                {
                    "confirmed_adults": list(confirmed_adults),
                    "r18_enabled_groups": list(r18_enabled_groups),
                },
                f,
                ensure_ascii=False,
                indent=2,
            )
    except Exception as e:
        print(f"[警告] 儲存 {DATA_FILE} 失敗: {e}")


_loaded = _load_data()

# ---- 暫存資料 ----
confirmed_adults: set[int] = _loaded["confirmed_adults"]
r18_enabled_groups: set[int] = _loaded["r18_enabled_groups"]
awaiting_keyword: dict[tuple, bool] = {}
pending_searches: dict[str, dict] = {}
_request_counter = 0
_counter_lock = asyncio.Lock()

# 去重快取: {(user_id, keyword_lower): set(illust_id, ...)}
seen_illust_cache: dict[tuple, set] = {}


async def _new_request_id() -> str:
    global _request_counter
    async with _counter_lock:
        _request_counter += 1
        return str(_request_counter)


def _is_group(update: Update) -> bool:
    return update.effective_chat.type in (ChatType.GROUP, ChatType.SUPERGROUP)


async def _is_group_admin(context: ContextTypes.DEFAULT_TYPE, chat_id: int, user_id: int) -> bool:
    try:
        member = await context.bot.get_chat_member(chat_id, user_id)
        return member.status in ("creator", "administrator")
    except Exception:
        return False


def _main_menu_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [[InlineKeyboardButton(SEARCH_BUTTON_TEXT, callback_data="menu:search")]]
    )


# ---------------------------------------------------------------------------
# 指令處理
# ---------------------------------------------------------------------------

async def handle_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (
        "👋 歡迎使用 Pixiv 搜圖機器人!\n\n"
        f"點擊下方「{SEARCH_BUTTON_TEXT}」按鈕開始搜尋,不需要打任何指令。\n\n"
        "其他指令:\n"
        "/confirm18 - (私訊)完成成年聲明,解鎖R-18選項\n"
        "/enable18 - (群組管理員)為此群組開啟R-18選項\n"
        "/disable18 - (群組管理員)為此群組關閉R-18選項"
    )
    await update.message.reply_text(text, reply_markup=_main_menu_keyboard())


async def handle_confirm18(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if _is_group(update):
        await update.message.reply_text(
            "⚠️ 這個指令僅能在與本Bot的私訊中使用。\n"
            "群組請改用 /enable18(需管理員權限)為整個群組開啟。",
        )
        return

    user_id = update.effective_user.id
    if user_id in confirmed_adults:
        await update.message.reply_text("✅ 你已經完成過成年聲明,可以直接使用R-18選項。")
        return

    markup = InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("✅ 我已年滿18歲,確認繼續", callback_data="confirm18:yes"),
                InlineKeyboardButton("❌ 取消", callback_data="confirm18:no"),
            ]
        ]
    )
    await update.message.reply_text(
        "⚠️ 聲明確認\n\n"
        "你即將解鎖可能包含成人向(R-18)內容的搜尋選項。\n"
        "點擊下方按鈕,即表示你聲明自己已年滿18歲,並理解相關內容可能不適合所有觀眾。",
        reply_markup=markup,
    )


async def handle_confirm18_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    choice = query.data.split(":")[1]
    user_id = query.from_user.id

    if choice == "yes":
        confirmed_adults.add(user_id)
        _save_data()
        await query.edit_message_text("✅ 聲明完成,你現在可以在私訊中使用R-18搜尋選項了。")
    else:
        await query.edit_message_text("已取消。")
    await query.answer()


async def handle_enable18(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _is_group(update):
        await update.message.reply_text("⚠️ 這個指令僅能在群組中使用。私訊請改用 /confirm18。")
        return

    chat_id = update.effective_chat.id
    user_id = update.effective_user.id
    if not await _is_group_admin(context, chat_id, user_id):
        await update.message.reply_text("⚠️ 只有群組管理員可以開啟此設定。")
        return

    r18_enabled_groups.add(chat_id)
    _save_data()
    await update.message.reply_text(
        "✅ 已為本群組開啟R-18搜尋選項。\n"
        "本群組所有成員之後搜圖時都會看到「R-18」「全部(不分級)」選項。\n"
        "管理員可隨時用 /disable18 關閉。",
    )


async def handle_disable18(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _is_group(update):
        await update.message.reply_text("⚠️ 這個指令僅能在群組中使用。")
        return

    chat_id = update.effective_chat.id
    user_id = update.effective_user.id
    if not await _is_group_admin(context, chat_id, user_id):
        await update.message.reply_text("⚠️ 只有群組管理員可以變更此設定。")
        return

    r18_enabled_groups.discard(chat_id)
    _save_data()
    await update.message.reply_text("✅ 已為本群組關閉R-18搜尋選項,之後僅提供全年齡內容。")


# ---------------------------------------------------------------------------
# 搜尋面板按鈕觸發
# ---------------------------------------------------------------------------

async def handle_search_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    key = (query.message.chat.id, query.from_user.id)
    awaiting_keyword[key] = True
    await query.edit_message_text("🔍 請直接輸入想搜尋的關鍵詞(直接打字傳送即可):")
    await query.answer()


async def handle_text_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    統一的文字訊息入口。
    這裡同時負責兩件事，依序判斷：
    1. 如果使用者正在「等待輸入Pixiv搜尋關鍵詞」的狀態 -> 視為關鍵詞，開始搜尋面板流程
    2. 否則 -> 視為一般訊息，交給連結修復功能去偵測有沒有社群連結
    這個順序很重要：避免使用者打關鍵詞時，剛好關鍵詞裡含有 http 字樣被誤判成連結。
    """
    if not update.message or not update.message.text:
        return

    key = (update.effective_chat.id, update.effective_user.id)

    # 舊版 ReplyKeyboard 按鈕殘留偵測(沿用原邏輯)
    if update.message.text.strip() == SEARCH_BUTTON_TEXT and not awaiting_keyword.get(key):
        await update.message.reply_text(
            "偵測到舊版選單按鈕,已為你移除。請改用 /start 叫出最新版選單。",
        )
        return

    if awaiting_keyword.get(key):
        awaiting_keyword.pop(key, None)
        keyword = update.message.text.strip()
        if not keyword:
            await update.message.reply_text(
                "⚠️ 關鍵詞不能是空白,請重新點選單開始。", reply_markup=_main_menu_keyboard()
            )
            return
        await _start_search_panel(update, context, keyword)
        return

    # 不是在等待關鍵詞輸入 -> 交給連結修復功能處理
    await fix_social_links(update, context)


async def _start_search_panel(update: Update, context: ContextTypes.DEFAULT_TYPE, keyword: str):
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id
    is_group = _is_group(update)

    if is_group:
        can_use_r18 = chat_id in r18_enabled_groups
    else:
        can_use_r18 = user_id in confirmed_adults

    req_id = await _new_request_id()
    pending_searches[req_id] = {
        "keyword": keyword,
        "count": None,
        "rating": None,
        "chat_id": chat_id,
        "user_id": user_id,
        "can_use_r18": can_use_r18,
    }

    markup = _build_count_keyboard(req_id)

    if is_group and not can_use_r18:
        hint = "\n（本群組僅提供全年齡內容,管理員可用 /enable18 開啟更多選項)"
    elif not is_group and not can_use_r18:
        hint = "\n（如需R-18選項,請先使用 /confirm18 完成聲明)"
    else:
        hint = ""

    await update.message.reply_text(
        f"🔍 搜尋關鍵詞:{keyword}\n請先選擇張數:{hint}",
        reply_markup=markup,
    )


def _build_count_keyboard(req_id: str) -> InlineKeyboardMarkup:
    row = [
        InlineKeyboardButton(f"{n}張", callback_data=f"count:{req_id}:{n}")
        for n in COUNT_OPTIONS
    ]
    return InlineKeyboardMarkup([row])


def _build_rating_keyboard(req_id: str, can_use_r18: bool) -> InlineKeyboardMarkup:
    buttons = [InlineKeyboardButton("全年齡", callback_data=f"rating:{req_id}:sfw")]
    if can_use_r18:
        buttons.append(InlineKeyboardButton("R-18", callback_data=f"rating:{req_id}:r18"))
        buttons.append(InlineKeyboardButton("全部(不分級)", callback_data=f"rating:{req_id}:all"))
    return InlineKeyboardMarkup([buttons])


async def handle_count_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    _, req_id, n = query.data.split(":")
    state = pending_searches.get(req_id)

    if state is None:
        await query.answer("⚠️ 這個搜尋已過期,請重新點選單搜尋。", show_alert=True)
        return
    if query.from_user.id != state["user_id"]:
        await query.answer("⚠️ 只有發起搜尋的人可以操作。", show_alert=True)
        return

    state["count"] = int(n)

    markup = _build_rating_keyboard(req_id, state["can_use_r18"])
    await query.edit_message_text(
        f"🔍 搜尋關鍵詞:{state['keyword']}\n已選張數:{state['count']}張\n請選擇分級:",
        reply_markup=markup,
    )
    await query.answer()


async def handle_rating_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    _, req_id, rating = query.data.split(":")
    state = pending_searches.get(req_id)

    if state is None:
        await query.answer("⚠️ 這個搜尋已過期,請重新點選單搜尋。", show_alert=True)
        return
    if query.from_user.id != state["user_id"]:
        await query.answer("⚠️ 只有發起搜尋的人可以操作。", show_alert=True)
        return

    if rating in ("r18", "all") and not state["can_use_r18"]:
        rating = "sfw"

    state["rating"] = rating

    await query.edit_message_text(
        f"🔍 搜尋關鍵詞:{state['keyword']}\n"
        f"張數:{state['count']}張 | 分級:{_rating_label(rating)}\n"
        f"✅ 搜尋中,請稍候...",
    )
    await query.answer()

    # 背景執行搜尋，不卡住事件迴圈對其他訊息的回應
    asyncio.create_task(
        _run_search_and_send(
            context, state["chat_id"], state["user_id"], state["keyword"], state["count"], rating
        )
    )

    pending_searches.pop(req_id, None)


def _rating_label(mode: str) -> str:
    return {"sfw": "全年齡", "r18": "R-18", "all": "全部(不分級)"}.get(mode, "未知")


# ---------------------------------------------------------------------------
# 精準搜尋核心 (翻5頁，確保關鍵字有效且擴大水池)
# 注意：這個函式本身維持同步寫法（呼叫 pixivpy3 也是同步的），
# 呼叫端一律用 asyncio.to_thread 包起來丟到背景執行緒跑，
# 避免卡住 bot 的事件迴圈。
# ---------------------------------------------------------------------------

def _search_pixiv(keyword: str, max_pages: int = 5):
    all_illusts = []
    try:
        # search_target 改用 Pixiv 官方App預設的 partial_match_for_tags。
        # title_and_caption 容易撈到「標題/簡介剛好擦邊提到關鍵詞」但其實不相關的作品，
        # 也容易漏掉「只有tag對得上」的相關作品。
        result = pixiv_api.search_illust(word=keyword, search_target="partial_match_for_tags")
        page_count = len(result.get("illusts", []))
        print(f"[搜尋] keyword={keyword!r} page=1 search_target=partial_match_for_tags 取得={page_count}張")
        if "illusts" in result:
            all_illusts.extend(result["illusts"])

        next_url = result.get("next_url")
        page = 1
        # 翻頁，撈取多頁原始資料，防止過濾後張數不夠
        while next_url and page < max_pages:
            next_qs = pixiv_api.parse_qs(next_url)

            # 強制在翻頁參數中注入關鍵字，防止 Pixiv API 在翻頁時洗掉搜尋條件
            if "word" not in next_qs:
                next_qs["word"] = keyword

            result = pixiv_api.search_illust(**next_qs)
            page_count = len(result.get("illusts", []))
            page += 1
            print(f"[搜尋] keyword={keyword!r} page={page} 取得={page_count}張 next_qs={next_qs}")
            if "illusts" in result:
                all_illusts.extend(result["illusts"])
            next_url = result.get("next_url")
    except Exception as e:
        print(f"[Pixiv API 錯誤] keyword={keyword!r} error={e}")

    # 除錯用：把撈到的作品標題印出來，方便判斷是否真的跟關鍵詞相關
    titles_preview = [i.get("title", "") for i in all_illusts[:20]]
    print(f"[搜尋結果預覽] keyword={keyword!r} 總數={len(all_illusts)} 前20筆標題={titles_preview}")

    return all_illusts


def _download_image(img_url: str) -> bytes:
    """同步下載圖片內容，呼叫端用 asyncio.to_thread 包裝"""
    resp = requests.get(
        img_url,
        headers={
            "Referer": "https://www.pixiv.net/",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        },
        timeout=15,
    )
    resp.raise_for_status()
    return resp.content


async def _run_search_and_send(
    context: ContextTypes.DEFAULT_TYPE,
    chat_id: int,
    user_id: int,
    keyword: str,
    count: int,
    rating_mode: str,
):
    try:
        illusts = await asyncio.to_thread(_search_pixiv, keyword)
    except Exception as e:
        await context.bot.send_message(chat_id, f"❌ 搜尋時發生錯誤:{e}", reply_markup=_main_menu_keyboard())
        return

    if not illusts:
        await context.bot.send_message(
            chat_id,
            f"😢 找不到「{keyword}」相關的作品,換個關鍵詞試試?",
            reply_markup=_main_menu_keyboard(),
        )
        return

    raw_count = len(illusts)

    # 分級篩選
    if rating_mode == "sfw":
        illusts = [i for i in illusts if i.get("x_restrict", 0) == 0]
    elif rating_mode == "r18":
        illusts = [i for i in illusts if i.get("x_restrict", 0) == 1]

    print(
        f"[分級過濾] keyword={keyword!r} rating={rating_mode} "
        f"過濾前={raw_count}張 過濾後={len(illusts)}張"
    )

    if not illusts:
        await context.bot.send_message(
            chat_id,
            f"😶 搜尋結果經過濾後沒有符合 {rating_mode.upper()} 條件的作品,換個關鍵詞試試?",
            reply_markup=_main_menu_keyboard(),
        )
        return

    # 將過濾後的結果全面隨機打亂，確保每次點擊都是完全不同的驚喜
    random.shuffle(illusts)

    cache_key = (user_id, keyword.lower())
    seen_ids = seen_illust_cache.setdefault(cache_key, set())

    unseen = [i for i in illusts if i.get("id") not in seen_ids]

    # 如果沒看過的圖不夠了，就清空去重快取重新循環，確保能盡量湊滿使用者要的張數
    if len(unseen) < count:
        seen_ids.clear()
        unseen = illusts

    # 從符合條件的水池中抽取對應張數;水池不足時只能給池子裡有的全部
    pool_size = len(unseen)
    actual_count = min(count, pool_size)
    results = random.sample(unseen, actual_count)

    print(
        f"[抽樣] keyword={keyword!r} rating={rating_mode} "
        f"要求張數={count} 水池大小={pool_size} 實際給予={actual_count}"
    )

    for illust in results:
        seen_ids.add(illust.get("id"))

    if actual_count < count:
        await context.bot.send_message(
            chat_id,
            f"⚠️ 「{keyword}」在目前分級({_rating_label(rating_mode)})下,"
            f"符合條件的作品只找到 {actual_count} 張(你選了{count}張)。"
            f"已將找到的全部送出。",
        )

    for idx, illust in enumerate(results, start=1):
        title = illust.get("title", "無標題")
        author = illust.get("user", {}).get("name", "未知作者")
        illust_id = illust.get("id")
        restrict = illust.get("x_restrict", 0)
        tag_label = RESTRICT_LABEL.get(restrict, "未知分級")

        image_urls = illust.get("image_urls", {})
        img_url = image_urls.get("large") or image_urls.get("medium")

        caption = (
            f"{title}\n"
            f"作者:{author} | 分級:{tag_label}\n"
            f"https://www.pixiv.net/artworks/{illust_id}\n"
            f"({idx}/{len(results)})"
        )

        if not img_url:
            await context.bot.send_message(chat_id, caption)
            continue

        try:
            content = await asyncio.to_thread(_download_image, img_url)
            await context.bot.send_photo(chat_id, photo=content, caption=caption)
        except Exception as e:
            print(f"[圖片下載/傳送失敗] illust_id={illust_id} url={img_url} error={e}")
            await context.bot.send_message(
                chat_id,
                caption + f"\n(圖片載入失敗:{type(e).__name__}: {e}\n請點擊上方連結查看)",
            )

    await context.bot.send_message(chat_id, "搜尋完成 ✅", reply_markup=_main_menu_keyboard())


# ============================================================
# 主程式
# ============================================================

def main():
    application = Application.builder().token(BOT_TOKEN).build()

    # --- 指令 ---
    application.add_handler(CommandHandler("start", handle_start))
    application.add_handler(CommandHandler("help", handle_start))
    application.add_handler(CommandHandler("confirm18", handle_confirm18))
    application.add_handler(CommandHandler("enable18", handle_enable18))
    application.add_handler(CommandHandler("disable18", handle_disable18))

    # --- 按鈕 callback (用 pattern 區分，避免互相搶單) ---
    application.add_handler(CallbackQueryHandler(handle_search_button, pattern=r"^menu:search$"))
    application.add_handler(CallbackQueryHandler(handle_confirm18_callback, pattern=r"^confirm18:"))
    application.add_handler(CallbackQueryHandler(handle_count_callback, pattern=r"^count:"))
    application.add_handler(CallbackQueryHandler(handle_rating_callback, pattern=r"^rating:"))

    # --- 文字訊息：統一入口，內部會分流到「Pixiv關鍵詞輸入」或「連結修復」---
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text_message))

    print("====================================================")
    print(" 🚀【FixTweet + Pixiv搜圖 合併整合版】機器人已成功啟動！")
    print(" 連結修復支援：X(Twitter)、Threads、IG、TikTok")
    print(" Pixiv搜圖：輸入 /start 開始")
    print("====================================================")
    application.run_polling()


if __name__ == "__main__":
    main()