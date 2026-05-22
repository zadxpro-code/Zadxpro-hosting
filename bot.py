#!/usr/bin/env python3
"""
╔══════════════════════════════════════════════════╗
║   ⚡ ZADXPRO — Bot Server Manager v2.0           ║
║   Ҳама кнопка · Анимация · Зебо · Тоза          ║
╚══════════════════════════════════════════════════╝
"""

import os, sys, shutil, subprocess, asyncio, logging
from pathlib import Path
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, BotCommand
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes
from telegram.error import BadRequest

# ━━━━━━━━━━━━━━━━━━ CONFIG ━━━━━━━━━━━━━━━━━━
BOT_TOKEN  = os.getenv("BOT_TOKEN", "8787496445:AAFKrV_Lm_55YriYb8Y6KVG56_HPEbv74ns")
ADMIN_IDS  = [int(x) for x in os.getenv("ADMIN_IDS", "7424107874").split(",") if x.strip()]
UPLOAD_DIR = Path("uploads")
UPLOAD_DIR.mkdir(exist_ok=True)

running: dict[int, subprocess.Popen] = {}

logging.basicConfig(format="%(asctime)s | %(levelname)s | %(message)s", level=logging.INFO)
log = logging.getLogger(__name__)

ALLOWED_EXT = {".py", ".js", ".sh", ".ts", ".rb"}

# ━━━━━━━━━━━━━━━━━━ DESIGN ━━━━━━━━━━━━━━━━━━
LINE  = "━━━━━━━━━━━━━━━━━━━━"
SLINE = "──────────────────────"

def progress_bar(pct: int, width: int = 10) -> str:
    filled = round(width * pct / 100)
    bar = "█" * filled + "░" * (width - filled)
    return f"[{bar}] {pct}%"

ANIM_FRAMES = [
    "⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"
]

# ━━━━━━━━━━━━━━━━━━ HELPERS ━━━━━━━━━━━━━━━━━━
def is_admin(uid: int) -> bool:
    return uid in ADMIN_IDS

def is_running(uid: int) -> bool:
    p = running.get(uid)
    return p is not None and p.poll() is None

def kill_user(uid: int):
    p = running.pop(uid, None)
    if p and p.poll() is None:
        p.terminate()
        try: p.wait(timeout=3)
        except subprocess.TimeoutExpired: p.kill()

def user_dir(uid: int) -> Path:
    d = UPLOAD_DIR / str(uid)
    d.mkdir(exist_ok=True)
    return d

def get_runner(filename: str) -> str:
    ext = Path(filename).suffix.lower()
    return {
        ".py": "python3",
        ".js": "node",
        ".sh": "bash",
        ".ts": "ts-node",
        ".rb": "ruby",
    }.get(ext, "python3")

async def safe_edit(msg, text, kb=None, parse_mode="Markdown"):
    try:
        await msg.edit_text(text, reply_markup=kb, parse_mode=parse_mode)
    except BadRequest:
        pass

# ━━━━━━━━━━━━━━━━━━ ANIMATIONS ━━━━━━━━━━━━━━━━━━
async def anim_loading(msg, label: str, steps=12, delay=0.18):
    for i in range(steps):
        frame = ANIM_FRAMES[i % len(ANIM_FRAMES)]
        try:
            await msg.edit_text(f"{frame} *{label}*", parse_mode="Markdown")
        except BadRequest:
            break
        await asyncio.sleep(delay)

async def anim_progress(msg, label: str, milestones: list[tuple[int,str]], delay=0.6):
    for pct, step_text in milestones:
        bar = progress_bar(pct)
        try:
            await msg.edit_text(
                f"⚡ *{label}*\n\n"
                f"`{bar}`\n\n"
                f"› {step_text}",
                parse_mode="Markdown"
            )
        except BadRequest:
            break
        await asyncio.sleep(delay)

async def anim_dots(msg, label: str, steps=6, delay=0.4):
    dots_frames = ["●○○", "●●○", "●●●", "○●●", "○○●", "○○○"]
    for i in range(steps):
        try:
            await msg.edit_text(
                f"  {dots_frames[i % len(dots_frames)]}  *{label}*",
                parse_mode="Markdown"
            )
        except BadRequest:
            break
        await asyncio.sleep(delay)

# ━━━━━━━━━━━━━━━━━━ KEYBOARDS ━━━━━━━━━━━━━━━━━━
def kb_main_menu(uid: int) -> InlineKeyboardMarkup:
    buttons = [
        [InlineKeyboardButton("📊 Вазъ", callback_data="menu_status"),
         InlineKeyboardButton("📂 Файлҳо", callback_data="menu_files")],
        [InlineKeyboardButton("🛑 Бозмондан", callback_data="menu_stop"),
         InlineKeyboardButton("ℹ️ Маълумот", callback_data="menu_info")],
    ]
    if is_admin(uid):
        buttons.append([
            InlineKeyboardButton("👑 Admin Panel", callback_data="menu_admin"),
        ])
    return InlineKeyboardMarkup(buttons)

def kb_confirm_start() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🚀  ХА — СТАРТ!", callback_data="confirm_yes"),
         InlineKeyboardButton("❌  НЕ", callback_data="confirm_no")],
    ])

def kb_admin_done_more() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("✅  Тамом — Старт!", callback_data="done_upload"),
         InlineKeyboardButton("➕  Боз файл", callback_data="more_files")],
        [InlineKeyboardButton("🗑  Ҳама нест кун", callback_data="cancel_upload")],
    ])

def kb_back_main() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🏠 Меню", callback_data="menu_main")]
    ])

def kb_stop_confirm() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🛑  Ха, бозмон!", callback_data="stop_yes"),
         InlineKeyboardButton("↩️  Не, бозгард", callback_data="menu_main")],
    ])

def kb_admin_panel(ctx) -> InlineKeyboardMarkup:
    active = [(uid, p) for uid, p in running.items() if p.poll() is None]
    rows = []
    for uid, _ in active:
        rows.append([InlineKeyboardButton(f"🛑 Kill › {uid}", callback_data=f"kill_{uid}")])
    rows.append([
        InlineKeyboardButton("💣 Kill ALL", callback_data="killall"),
        InlineKeyboardButton("↩️ Бозгард", callback_data="menu_main"),
    ])
    return InlineKeyboardMarkup(rows)

def kb_after_start() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🛑 Бозмондан", callback_data="menu_stop"),
         InlineKeyboardButton("📊 Вазъ", callback_data="menu_status")],
        [InlineKeyboardButton("📋 Лог (хатоҳо)", callback_data="menu_log"),
         InlineKeyboardButton("🏠 Меню", callback_data="menu_main")],
    ])

# ━━━━━━━━━━━━━━━━━━ SCREENS ━━━━━━━━━━━━━━━━━━
def screen_home(uid: int, first_name: str) -> str:
    role = "👑 *ADMIN*" if is_admin(uid) else "👤 *Корбар*"
    status = "🟢 Бот фаъол" if is_running(uid) else "🔴 Бот нест"
    return (
        f"⚡ *BOT SERVER MANAGER*\n"
        f"`by ZADXPRO`\n"
        f"{LINE}\n"
        f"Хуш омадӣ, *{first_name}*!\n"
        f"Нақш: {role}\n"
        f"Ҳолат: {status}\n"
        f"{LINE}\n"
        f"📤 Барои бор кардан — *файл фиристед*"
    )

def screen_status(uid: int, ud: dict) -> str:
    if is_running(uid):
        cmd = ud.get("running_cmd", "?")
        files = ud.get("uploaded_files", [])
        flist = "\n".join(f"  ✦ `{f}`" for f in files) if files else "  —"
        return (
            f"📊 *ВАЗЪИ БОТ*\n"
            f"{LINE}\n"
            f"🟢 *Фаъол*\n\n"
            f"▶️ Команда:\n`{cmd}`\n\n"
            f"📄 Файлҳо:\n{flist}\n"
            f"{SLINE}\n"
            f"🛑 Барои бозмондан тугмаро пахш кунед"
        )
    else:
        return (
            f"📊 *ВАЗЪИ БОТ*\n"
            f"{LINE}\n"
            f"🔴 *Ботеро кор намекунад*\n\n"
            f"📤 Барои оғоз файл фиристед"
        )

def screen_files(uid: int, ud: dict) -> str:
    pending = ud.get("pending_files", [])
    uploaded = ud.get("uploaded_files", [])
    text = f"📂 *ФАЙЛҲО*\n{LINE}\n"
    if pending:
        text += f"⏳ *Дар интизор ({len(pending)}):*\n"
        for f in pending:
            text += f"  📄 `{f}`\n"
        text += "\n"
    if uploaded and is_running(uid):
        text += f"✅ *Дар кор ({len(uploaded)}):*\n"
        for f in uploaded:
            text += f"  🟢 `{f}`\n"
    if not pending and not uploaded:
        text += "📭 Ҳеҷ файле нест\n\n📤 Файл фиристед"
    return text

def screen_info(uid: int) -> str:
    limit = "Бе маҳдудият" if is_admin(uid) else "1 файл"
    role = "👑 Admin" if is_admin(uid) else "👤 Корбар"
    return (
        f"ℹ️ *МАЪЛУМОТ*\n"
        f"{LINE}\n"
        f"🤖 *Bot Server Manager*\n"
        f"`ZADXPRO · v2.0`\n\n"
        f"👤 Нақши шумо: *{role}*\n"
        f"📁 Маҳдудият: *{limit}*\n\n"
        f"*Командаҳо:*\n"
        f"• Файл фиристед → бор кунад\n"
        f"• Тугмаи 📊 → вазъ бубинед\n"
        f"• Тугмаи 🛑 → ботро бозмонед\n"
        + (
            f"\n*Барои Admin:*\n"
            f"• Чандин файл бор кунед\n"
            f"• Kill ҳар як корбар\n"
            if is_admin(uid) else ""
        )
    )

# ━━━━━━━━━━━━━━━━━━ LAUNCH BOT ━━━━━━━━━━━━━━━━━━
async def launch_bot(send_to, ctx: ContextTypes.DEFAULT_TYPE, uid: int, cmd: str, is_edit=True):
    ud = ctx.user_data
    d  = user_dir(uid)

    milestones = [
        (10,  "Файлҳо тайёр карда мешаванд..."),
        (35,  "Муҳит танзим мешавад..."),
        (60,  "Вобастагиҳо тафтиш мешаванд..."),
        (85,  f"Иҷро мешавад: `{cmd}`"),
        (100, "Бот оғоз шуд! ✓"),
    ]

    try:
        if is_edit:
            await anim_progress(send_to, "БОТ СТАРТ ШУДА ИСТОДААСТ", milestones)
        else:
            init_msg = await send_to.reply_text("⠋ *Оғоз...*", parse_mode="Markdown")
            await anim_progress(init_msg, "БОТ СТАРТ ШУДА ИСТОДААСТ", milestones)
            send_to = init_msg

        # ── Stderr-ро ба файл нависед (хатоҳо пинҳон намешаванд) ──
        log_path = d / "bot_stderr.log"
        log_file = open(log_path, "w", encoding="utf-8")

        proc = subprocess.Popen(
            cmd.split(),
            cwd=str(d),
            stdout=log_file,
            stderr=log_file,
        )
        running[uid] = proc
        ud["running_cmd"] = cmd
        ud["log_path"] = str(log_path)
        files = ud.get("pending_files", [])
        ud["uploaded_files"] = files
        ud.pop("pending_files", None)
        ud.pop("waiting_for_cmd", None)

        # ── 2 сония интизор — агар бот фавран мирад хаторо нишон деҳ ──
        await asyncio.sleep(2)
        log_file.flush()

        if proc.poll() is not None:
            # Бот старт нашуд / фавран мурд
            running.pop(uid, None)
            log_file.close()
            try:
                error_text = Path(log_path).read_text(encoding="utf-8", errors="replace")
                error_short = error_text[-900:] if len(error_text) > 900 else error_text
                if not error_short.strip():
                    error_short = "Лог холӣ аст — эҳтимол python3/node ёфт нашуд"
            except Exception:
                error_short = "Лог хонда нашуд"

            await safe_edit(send_to,
                f"❌ *БОТ СТАРТ НАШУД!*\n"
                f"{LINE}\n"
                f"📋 Хато:\n```\n{error_short}\n```",
                kb_back_main()
            )
            return

        log.info(f"[{uid}] launched: {cmd}")

        pending_files = "\n".join(f"  ✦ `{f}`" for f in files) if files else "  —"
        final_text = (
            f"🚀 *БОТ СТАРТ ШУД!*\n"
            f"{LINE}\n"
            f"🟢 *Фаъол*\n\n"
            f"▶️ Команда:\n`{cmd}`\n\n"
            f"📄 Файлҳо:\n{pending_files}\n"
            f"{SLINE}\n"
            f"🛑 Барои бозмондан тугмаро пахш кунед"
        )
        await asyncio.sleep(0.3)
        await safe_edit(send_to, final_text, kb_after_start())

    except FileNotFoundError:
        await safe_edit(send_to,
            f"❌ *Хато!*\n{LINE}\n"
            f"Команда `{cmd}` ёфт нашуд.\n"
            f"Тафтиш кунед файл дуруст аст.",
            kb_back_main()
        )
    except Exception as e:
        log.error(f"[{uid}] launch error: {e}")
        await safe_edit(send_to, f"❌ *Хато:*\n`{e}`", kb_back_main())

# ━━━━━━━━━━━━━━━━━━ /start ━━━━━━━━━━━━━━━━━━
async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    u = update.effective_user
    msg = await update.message.reply_text("⠋ *Оғоз...*", parse_mode="Markdown")
    await anim_dots(msg, "Бор карда мешавад", steps=4, delay=0.3)
    await asyncio.sleep(0.2)
    await safe_edit(msg, screen_home(u.id, u.first_name), kb_main_menu(u.id))

# ━━━━━━━━━━━━━━━━━━ FILE RECEIVED ━━━━━━━━━━━━━━━━━━
async def on_file(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid  = update.effective_user.id
    doc  = update.message.document
    if not doc:
        return

    filename = doc.file_name or "bot.py"
    ext = Path(filename).suffix.lower()

    if not is_admin(uid) and is_running(uid):
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("🛑 Бозмондан", callback_data="menu_stop"),
             InlineKeyboardButton("📊 Вазъ", callback_data="menu_status")],
        ])
        await update.message.reply_text(
            f"⛔ *Имкон нест!*\n"
            f"{LINE}\n"
            f"Шумо аллакай як бот доред.\n\n"
            f"🛑 Аввал бозмонед, баъд файли нав фиристед.",
            reply_markup=kb,
            parse_mode="Markdown",
        )
        return

    if ext not in ALLOWED_EXT:
        await update.message.reply_text(
            f"❌ *Файл қабул нашуд!*\n"
            f"{LINE}\n"
            f"📄 `{filename}`\n\n"
            f"✅ Иҷозат дода шудааст:\n"
            f"`.py`  `.js`  `.sh`  `.ts`  `.rb`",
            reply_markup=kb_back_main(),
            parse_mode="Markdown",
        )
        return

    msg = await update.message.reply_text("⠋ *Файл бор карда мешавад...*", parse_mode="Markdown")
    await anim_loading(msg, "Боркунӣ", steps=8, delay=0.15)

    tg_file = await ctx.bot.get_file(doc.file_id)
    save_path = user_dir(uid) / filename
    await tg_file.download_to_drive(save_path)

    pending: list = ctx.user_data.setdefault("pending_files", [])
    if filename not in pending:
        pending.append(filename)

    count = len(pending)
    flist = "\n".join(f"  ✦ `{f}`" for f in pending)

    if is_admin(uid):
        await safe_edit(msg,
            f"📦 *ФАЙЛҲО БОР ШУДАНД*\n"
            f"{LINE}\n"
            f"📁 Ҳисоб: *{count} файл*\n\n"
            f"{flist}\n\n"
            f"{SLINE}\n"
            f"Боз файл фиристед ё тугмаро пахш кунед:",
            kb_admin_done_more()
        )
    else:
        await safe_edit(msg,
            f"✅ *ФАЙЛ ҚАБУЛ ШУД*\n"
            f"{LINE}\n"
            f"📄 `{filename}`\n\n"
            f"🤖 Ботро старт кунам?",
            kb_confirm_start()
        )

# ━━━━━━━━━━━━━━━━━━ TEXT ━━━━━━━━━━━━━━━━━━
async def on_text(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    ud  = ctx.user_data
    uid = update.effective_user.id
    if not ud.get("waiting_for_cmd"):
        return

    cmd = update.message.text.strip()
    if not cmd:
        return

    ud.pop("waiting_for_cmd", None)
    msg = await update.message.reply_text("⠋ *Тайёр шуда истодааст...*", parse_mode="Markdown")
    await launch_bot(msg, ctx, uid, cmd, is_edit=True)

# ━━━━━━━━━━━━━━━━━━ CALLBACKS ━━━━━━━━━━━━━━━━━━
async def on_callback(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q   = update.callback_query
    await q.answer()
    uid  = q.from_user.id
    ud   = ctx.user_data
    data = q.data

    # ── Admin kill ──
    if data.startswith("kill_"):
        if not is_admin(uid): return
        target = int(data[5:])
        msg = q.message
        await anim_dots(msg, f"Kill {target}", steps=4, delay=0.3)
        if is_running(target):
            kill_user(target)
            await safe_edit(msg,
                f"🛑 *Бозмонда шуд!*\n{LINE}\n"
                f"👤 Корбари `{target}` бозмонда шуд.",
                kb_admin_panel(ctx)
            )
        else:
            await safe_edit(msg, f"⭕ Корбари `{target}` бот надошт.", kb_admin_panel(ctx))
        return

    # ── Menu: Main ──
    if data == "menu_main":
        name = q.from_user.first_name
        await safe_edit(q.message, screen_home(uid, name), kb_main_menu(uid))

    # ── Menu: Status ──
    elif data == "menu_status":
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("🔄 Янгила", callback_data="menu_status")],
            [InlineKeyboardButton("🛑 Бозмондан", callback_data="menu_stop"),
             InlineKeyboardButton("🏠 Меню", callback_data="menu_main")],
        ])
        await safe_edit(q.message, screen_status(uid, ud), kb)

    # ── Menu: Files ──
    elif data == "menu_files":
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("🗑 Нест кун", callback_data="cancel_upload"),
             InlineKeyboardButton("🏠 Меню", callback_data="menu_main")],
        ])
        await safe_edit(q.message, screen_files(uid, ud), kb)

    # ── Menu: Info ──
    elif data == "menu_info":
        await safe_edit(q.message, screen_info(uid), kb_back_main())

    # ── Menu: Stop ──
    elif data == "menu_stop":
        if is_running(uid):
            await safe_edit(q.message,
                f"🛑 *БОЗМОНДАН*\n{LINE}\n"
                f"Боти худро бозмондан мехоҳед?",
                kb_stop_confirm()
            )
        else:
            await safe_edit(q.message,
                f"⭕ *Ботеро кор намекунад*\n{LINE}\n"
                f"Ҳеҷ чиз бозмондан лозим нест.",
                kb_back_main()
            )

    # ── Menu: Log ── (НАВИ — хатоҳоро нишон медиҳад)
    elif data == "menu_log":
        log_path = ud.get("log_path")
        if not log_path:
            await safe_edit(q.message,
                f"📋 *ЛОГ*\n{LINE}\nЛог ёфт нашуд.",
                kb_back_main()
            )
            return
        try:
            text = Path(log_path).read_text(encoding="utf-8", errors="replace")
            last = text[-800:] if len(text) > 800 else text
            if not last.strip():
                last = "Лог ҳоло холӣ аст (бот тоза старт шуд)"
        except Exception:
            last = "Лог хонда нашуд"
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("🔄 Янгила", callback_data="menu_log"),
             InlineKeyboardButton("🏠 Меню", callback_data="menu_main")],
        ])
        await safe_edit(q.message,
            f"📋 *ЛОГ (охирин 800 символ)*\n{LINE}\n```\n{last}\n```",
            kb
        )

    # ── Stop confirmed ──
    elif data == "stop_yes":
        msg = q.message
        await anim_dots(msg, "Бозмонда мешавад", steps=5, delay=0.3)
        kill_user(uid)
        ud.pop("running_cmd", None)
        ud.pop("uploaded_files", None)
        ud.pop("pending_files", None)
        ud.pop("log_path", None)
        shutil.rmtree(user_dir(uid), ignore_errors=True)
        await asyncio.sleep(0.3)
        await safe_edit(msg,
            f"✅ *Бозмонда шуд!*\n"
            f"{LINE}\n"
            f"🔴 Бот бозмонда шуд.\n\n"
            f"📤 Файли нав фиристед.",
            kb_back_main()
        )

    # ── Admin panel ──
    elif data == "menu_admin":
        if not is_admin(uid): return
        active = [(u, p) for u, p in running.items() if p.poll() is None]
        lines = "\n".join(f"  🟢 `{u}`" for u, _ in active) if active else "  🔴 Ҳеҷ кас"
        await safe_edit(q.message,
            f"👑 *ADMIN PANEL*\n"
            f"{LINE}\n"
            f"📊 Фаъол: *{len(active)} та*\n\n"
            f"{lines}\n"
            f"{SLINE}\n"
            f"Kill тугмаи корбарро пахш кунед:",
            kb_admin_panel(ctx)
        )

    # ── Kill all ──
    elif data == "killall":
        if not is_admin(uid): return
        msg = q.message
        await anim_progress(msg, "ҲАМАРО БОЗМОНДА ИСТОДААСТ",
            [(30, "Ботҳо ёфта мешаванд..."),
             (70, "Равандҳо хотима меёбанд..."),
             (100, "Тамом!")],
            delay=0.5
        )
        count = sum(1 for u in list(running) if running.get(u) and running[u].poll() is None)
        for u in list(running.keys()):
            kill_user(u)
        await asyncio.sleep(0.4)
        await safe_edit(msg,
            f"💣 *ҲАМА БОЗМОНДА ШУД!*\n{LINE}\n"
            f"🛑 {count} та бот бозмонда шуд.",
            kb_back_main()
        )

    # ── More files (admin) ──
    elif data == "more_files":
        count = len(ud.get("pending_files", []))
        await safe_edit(q.message,
            f"📤 *ФАЙЛ ФИРИСТЕД*\n{LINE}\n"
            f"Ҳозир: *{count}* файл бор шудааст.\n\n"
            f"Файли дигар фиристед..."
        )

    # ── Done upload (admin) ──
    elif data == "done_upload":
        files = ud.get("pending_files", [])
        if not files:
            await safe_edit(q.message, "❌ Ҳеҷ файле нест!", kb_back_main())
            return
        if len(files) == 1:
            runner = get_runner(files[0])
            await launch_bot(q.message, ctx, uid, f"{runner} {files[0]}", is_edit=True)
        else:
            ud["waiting_for_cmd"] = True
            flist = "\n".join(f"  ✦ `{f}`" for f in files)
            rows = [[InlineKeyboardButton(f"▶️ {get_runner(f)} {f}", callback_data=f"quickcmd_{get_runner(f)} {f}")] for f in files]
            rows.append([InlineKeyboardButton("🗑 Бекор кун", callback_data="cancel_upload")])
            await safe_edit(q.message,
                f"⌨️ *START COMMAND*\n"
                f"{LINE}\n"
                f"📂 Файлҳо ({len(files)}):\n{flist}\n\n"
                f"Поёнро пахш кунед ё дастӣ нависед:\n"
                f"Мисол: `python3 main.py`",
                InlineKeyboardMarkup(rows)
            )

    # ── Quick cmd pick ──
    elif data.startswith("quickcmd_"):
        cmd = data[9:]
        ud.pop("waiting_for_cmd", None)
        await launch_bot(q.message, ctx, uid, cmd, is_edit=True)

    # ── Confirm start (user) ──
    elif data == "confirm_yes":
        files = ud.get("pending_files", [])
        if files:
            runner = get_runner(files[0])
            await launch_bot(q.message, ctx, uid, f"{runner} {files[0]}", is_edit=True)
        else:
            await safe_edit(q.message, "❌ Файл ёфт нашуд!", kb_back_main())

    # ── Cancel ──
    elif data == "confirm_no" or data == "cancel_upload":
        ud.pop("pending_files", None)
        ud.pop("waiting_for_cmd", None)
        ud.pop("log_path", None)
        shutil.rmtree(user_dir(uid), ignore_errors=True)
        await safe_edit(q.message,
            f"🗑 *Бекор шуд*\n{LINE}\n"
            f"Ҳама файлҳо нест карда шуданд.\n\n"
            f"📤 Файли нав фиристед.",
            kb_back_main()
        )

# ━━━━━━━━━━━━━━━━━━ SETUP COMMANDS ━━━━━━━━━━━━━━━━━━
async def post_init(app: Application):
    await app.bot.set_my_commands([
        BotCommand("start", "🏠 Менюи асосӣ"),
    ])
    log.info("✅ Bot commands set.")

# ━━━━━━━━━━━━━━━━━━ MAIN ━━━━━━━━━━━━━━━━━━
def main():
    if not BOT_TOKEN:
        log.error("❌ BOT_TOKEN муайян нашудааст!")
        sys.exit(1)
    if not ADMIN_IDS:
        log.warning("⚠️ ADMIN_IDS муайян нашудааст!")

    app = (
        Application.builder()
        .token(BOT_TOKEN)
        .post_init(post_init)
        .build()
    )

    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(MessageHandler(filters.Document.ALL, on_file))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, on_text))
    app.add_handler(CallbackQueryHandler(on_callback))

    log.info("⚡ ZADXPRO Bot Server Manager v2.0 — started!")
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
