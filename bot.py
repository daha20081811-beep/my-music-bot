import asyncio
import os
import sqlite3
import subprocess
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.utils.keyboard import InlineKeyboardBuilder
import lyricsgenius
import yt_dlp

# Отримуємо токени з налаштувань Secrets на Hugging Face
TOKEN = os.getenv('BOT_TOKEN')
GENIUS_API_KEY = os.getenv('GENIUS_API_KEY')

bot = Bot(token=TOKEN)
dp = Dispatcher()
genius = lyricsgenius.Genius(GENIUS_API_KEY)

# База даних
conn = sqlite3.connect('users.db', check_same_thread=False)
cursor = conn.cursor()
cursor.execute('CREATE TABLE IF NOT EXISTS users (user_id INTEGER PRIMARY KEY, lang TEXT)')
conn.commit()

def get_lang(uid):
    cursor.execute('SELECT lang FROM users WHERE user_id = ?', (uid,))
    res = cursor.fetchone()
    return res[0] if res else 'uk'

translations = {
    'en': {'search': "Artist/song:", 'top_ua': "🇺🇦 Ukraine Hits", 'top_us': "🇺🇸 US Hits", 'dl': "📥 Download", 'wait': "⏳ Wait...", 'ring': "✂️ Ringtone"},
    'ru': {'search': "Артист/песня:", 'top_ua': "🇺🇦 Хиты Украины", 'top_us': "🇺🇸 Хиты США", 'dl': "📥 Скачать", 'wait': "⏳ Ждите...", 'ring': "✂️ Рингтон"},
    'uk': {'search': "Артист/пісня:", 'top_ua': "🇺🇦 Хіти України", 'top_us': "🇺🇸 Хіти США", 'dl': "📥 Завантажити", 'wait': "⏳ Зачекайте...", 'ring': "✂️ Рингтон"}
}

def get_menu(uid):
    l = get_lang(uid)
    kb = InlineKeyboardBuilder()
    kb.row(types.InlineKeyboardButton(text=translations[l]['top_ua'], callback_data="top_ua"))
    kb.row(types.InlineKeyboardButton(text=translations[l]['top_us'], callback_data="top_us"))
    return kb.as_markup()

@dp.message(Command("start"))
async def cmd_start(m: types.Message):
    kb = InlineKeyboardBuilder()
    kb.row(types.InlineKeyboardButton(text="🇺🇦", callback_data="l_uk"),
           types.InlineKeyboardButton(text="🇷🇺", callback_data="l_ru"),
           types.InlineKeyboardButton(text="🇺🇸", callback_data="l_en"))
    await m.answer("Select language:", reply_markup=kb.as_markup())

@dp.callback_query(F.data.startswith("l_"))
async def set_lang(c: types.CallbackQuery):
    l = c.data.split("_")[1]
    cursor.execute('INSERT OR REPLACE INTO users VALUES (?, ?)', (c.from_user.id, l))
    conn.commit()
    await c.answer()
    await c.message.delete()
    await c.message.answer(translations[l]['search'], reply_markup=get_menu(c.from_user.id))

@dp.callback_query(F.data.startswith("top_"))
async def show_top(c: types.CallbackQuery):
    l = get_lang(c.from_user.id)
    query = "Ukrainian Hits 2025" if "ua" in c.data else "Billboard Top 2025"
    await c.answer()
    res = genius.search_songs(query)
    for h in res['hits'][:5]:
        s = h['result']
        kb = InlineKeyboardBuilder()
        kb.row(types.InlineKeyboardButton(text=translations[l]['dl'], callback_data=f"d_{s['id']}"))
        await c.message.answer(f"🔥 {s['full_title']}", reply_markup=kb.as_markup())
    await c.message.answer(translations[l]['search'], reply_markup=get_menu(c.from_user.id))

@dp.message()
async def handle_search(m: types.Message):
    l = get_lang(m.from_user.id)
    wait = await m.answer("🔎 ...")
    try:
        res = genius.search_songs(m.text)
        if res and res['hits']:
            await wait.delete()
            for h in res['hits'][:5]:
                s = h['result']
                kb = InlineKeyboardBuilder()
                kb.row(types.InlineKeyboardButton(text=translations[l]['dl'], callback_data=f"d_{s['id']}"))
                await m.answer(f"🎵 {s['full_title']}", reply_markup=kb.as_markup())
            await m.answer(translations[l]['search'], reply_markup=get_menu(m.from_user.id))
        else: await wait.edit_text("❌ Not found")
    except: await wait.edit_text("❌ Error")

@dp.callback_query(F.data.startswith("d_"))
async def do_dl(c: types.CallbackQuery):
    l = get_lang(c.from_user.id)
    sid = c.data.split("_")[1]
    info = genius.song(sid)['song']
    title = info['full_title']
    msg = await c.message.answer(translations[l]['wait'])
    f_name = f"m_{sid}"
    ydl_opts = {'format': 'bestaudio/best', 'outtmpl': f_name, 'quiet': True,
                'postprocessors': [{'key': 'FFmpegExtractAudio','preferredcodec': 'mp3','preferredquality': '192'}]}
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl: ydl.download([f"ytsearch1:{title} audio"])
        kb = InlineKeyboardBuilder()
        kb.row(types.InlineKeyboardButton(text=translations[l]['ring'], callback_data=f"r_{f_name}"))
        # Помилку SyntaxError тут виправлено (дужка закрита коректно)
        await c.message.answer_audio(types.FSInputFile(f"{f_name}.mp3"), caption=f"✅ {title}", reply_markup=kb.as_markup())
        await msg.delete()
    except: await msg.edit_text("❌ Error DL")

@dp.callback_query(F.data.startswith("r_"))
async def do_ring(c: types.CallbackQuery):
    f = c.data[2:]
    in_f, out_f = f"{f}.mp3", f"ring_{f}.mp3"
    if os.path.exists(in_f):
        cmd = f'ffmpeg -y -ss 00:00:00 -t 00:00:30 -i "{in_f}" -acodec copy "{out_f}"'
        subprocess.run(cmd, shell=True)
        await c.message.answer_audio(types.FSInputFile(out_f), caption="🔔 Ringtone")
        if os.path.exists(out_f): os.remove(out_f)

async def main():
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
