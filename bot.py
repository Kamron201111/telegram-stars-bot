import logging
import json
import os
import random
from datetime import datetime, timedelta
from typing import Dict, List, Optional
from enum import Enum
import telebot
from telebot.types import (
    ReplyKeyboardMarkup, KeyboardButton,
    InlineKeyboardMarkup, InlineKeyboardButton
)
from dotenv import load_dotenv
import redis

load_dotenv()

# Loglash sozlamalari
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Konfiguratsiya (ENV o‘rniga bevosita qiymat qo‘ydim)
TOKEN = "7810689974:AAHpifjmAG_tOwDvIGRNG4L1ah8mix38cWU"
ADMIN_CHAT_ID = "6498632307"
SUPPORT_USERNAME = "@Kamron201"
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379")

# Botni ishga tushirish
bot = telebot.TeleBot(TOKEN)


# Konstanta holatlar
class OrderStatus(Enum):
    PENDING = "pending"
    PAID = "paid"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    PAYMENT_ERROR = "payment_error"


class UserRole(Enum):
    USER = "user"
    ADMIN = "admin"


# Stars paketlari (narx sonlari avvalgidek, faqat "so‘m" deb yozildi)
TELEGRAM_STARS_PACKAGES = {
    "buy_50": {"amount": 50, "price": 80, "points": 1, "discount": 0},
    "buy_75": {"amount": 75, "price": 130, "points": 2, "discount": 5},
    "buy_100": {"amount": 100, "price": 160, "points": 2, "discount": 10},
    "buy_250": {"amount": 250, "price": 380, "points": 4, "discount": 15},
    "buy_500": {"amount": 500, "price": 780, "points": 8, "discount": 20},
    "buy_750": {"amount": 750, "price": 1300, "points": 12, "discount": 25},
    "buy_1000": {"amount": 1000, "price": 1580, "points": 15, "discount": 30},
}

# Foydalanuvchi holatlari
user_states = {}


class SecurityManager:
    @staticmethod
    def validate_user_input(text: str, max_length: int = 100) -> bool:
        if not text or len(text) > max_length:
            return False
        dangerous_patterns = ['<script>', '../', ';', '--']
        return not any(pattern in text.lower() for pattern in dangerous_patterns)

    @staticmethod
    def generate_order_id() -> str:
        timestamp = int(datetime.now().timestamp())
        random_part = random.randint(1000, 9999)
        return f"ORD{timestamp}{random_part}"


class DatabaseManager:
    def __init__(self):
        try:
            self.redis_client = redis.from_url(REDIS_URL, decode_responses=True)
        except Exception:
            self.redis_client = None

    def get_user_data(self, user_id: int) -> Dict:
        try:
            if not self.redis_client:
                return self._get_default_user_data()

            key = f"user:{user_id}"
            data = self.redis_client.get(key)
            if data:
                return json.loads(data)

            default_data = self._get_default_user_data()
            self.update_user_data(user_id, default_data)
            return default_data
        except Exception as e:
            logger.error(f"Error getting user data: {e}")
            return self._get_default_user_data()

    def _get_default_user_data(self):
        return {
            "username": "",
            "total_stars": 0,
            "total_spent": 0,
            "points": 0,
            "orders_count": 0,
            "role": UserRole.USER.value,
            "registration_date": datetime.now().isoformat(),
            "last_activity": datetime.now().isoformat(),
            "notifications": True
        }

    def update_user_data(self, user_id: int, updates: Dict):
        try:
            if not self.redis_client:
                return

            key = f"user:{user_id}"
            current_data = self.get_user_data(user_id)
            current_data.update(updates)
            current_data["last_activity"] = datetime.now().isoformat()
            self.redis_client.set(key, json.dumps(current_data), ex=86400 * 30)
        except Exception as e:
            logger.error(f"Error updating user data: {e}")

    def create_order(self, order_data: Dict) -> str:
        try:
            if not self.redis_client:
                return SecurityManager.generate_order_id()

            order_id = SecurityManager.generate_order_id()
            order_data["order_id"] = order_id
            order_data["created_at"] = datetime.now().isoformat()
            order_data["status"] = OrderStatus.PENDING.value

            key = f"order:{order_id}"
            self.redis_client.set(key, json.dumps(order_data), ex=86400 * 7)

            return order_id
        except Exception as e:
            logger.error(f"Error creating order: {e}")
            return SecurityManager.generate_order_id()


# DB manager
db = DatabaseManager()


def get_user_role(user_id: int) -> UserRole:
    return UserRole.ADMIN if str(user_id) == ADMIN_CHAT_ID else UserRole.USER


# /start komandasi
@bot.message_handler(commands=['start'])
def start_handler(message):
    user_id = message.from_user.id
    user_role = get_user_role(user_id)

    db.update_user_data(user_id, {
        "username": message.from_user.username or "",
        "first_name": message.from_user.first_name or ""
    })

    if user_role == UserRole.ADMIN:
        keyboard = [
            [KeyboardButton("📊 Statistika"), KeyboardButton("📦 Buyurtmalar")],
            [KeyboardButton("👥 Foydalanuvchilar")]
        ]
    else:
        keyboard = [
            [KeyboardButton("🛒 Stars sotib olish"), KeyboardButton("👤 Profil")],
            [KeyboardButton("🆘 Yordam")]
        ]

    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

    welcome_text = (
        f"🌟 Assalomu alaykum, {message.from_user.first_name}!\n\n"
        "⚡ <b>Telegram Stars Bot</b> — tez va ishonchli Stars sotib olish xizmati\n\n"
        "✅ <b>Afzalliklar:</b>\n"
        "• 🚀 Yetkazib berish: 1–6 soat\n"
        "• 🎁 Bonus tizimi\n"
        "• 💎 Yetkazib berish kafolati\n"
        "• 🔒 Xavfsiz to‘lovlar\n\n"
        "Quyidagi menyudan amal tanlang 👇"
    )

    bot.send_message(message.chat.id, welcome_text, reply_markup=reply_markup, parse_mode='HTML')


# Stars paketlarini ko‘rsatish
@bot.message_handler(func=lambda message: message.text == "🛒 Stars sotib olish")
def show_stars_packages(message):
    keyboard = []
    for key, package in TELEGRAM_STARS_PACKAGES.items():
        discount_text = f" 🔥 -{package['discount']}%" if package['discount'] > 0 else ""
        button_text = f"{package['amount']} Stars — {package['price']} so‘m{discount_text}"
        keyboard.append([InlineKeyboardButton(button_text, callback_data=key)])

    reply_markup = InlineKeyboardMarkup(keyboard)

    info_text = (
        "🎯 <b>Telegram Stars miqdorini tanlang</b>\n\n"
        "⚡ <b>Yetkazib berish:</b> 1–6 soat\n"
        "💎 <b>Yetkazib berish kafolati</b>\n"
        "🎁 <b>Har bir xarid uchun bonus ballar!</b>\n\n"
        "🔥 <i>Katta paketlarga chegirmalar mavjud!</i>"
    )

    bot.send_message(message.chat.id, info_text, reply_markup=reply_markup, parse_mode='HTML')


# Paket tanlash callback
@bot.callback_query_handler(func=lambda call: call.data.startswith('buy_'))
def handle_package_selection(call):
    selected_package = TELEGRAM_STARS_PACKAGES.get(call.data)

    if selected_package:
        user_states[call.from_user.id] = {
            'current_order': selected_package,
            'step': 'waiting_username'
        }

        order_text = (
            f"🎯 <b>Siz tanladingiz:</b> {selected_package['amount']} Telegram Stars\n"
            f"💰 <b>To‘lov summasi:</b> {selected_package['price']} so‘m\n"
            f"🎁 <b>Bonus ballar:</b> {selected_package['points']}\n"
        )

        if selected_package['discount'] > 0:
            order_text += f"🔥 <b>Chegirma:</b> {selected_package['discount']}%\n"

        order_text += (
            "\n📝 <b>Telegram username’ingizni yuboring (@siz):</b>\n\n"
            "⚠ <b>DIQQAT:</b>\n"
            "• Username ochiq (public) bo‘lishi kerak\n"
            "• To‘g‘ri yozilganiga ishonch hosil qiling"
        )

        bot.edit_message_text(order_text, call.message.chat.id, call.message.message_id, parse_mode='HTML')
    else:
        bot.edit_message_text(
            "❌ Xatolik yuz berdi. Iltimos, qaytadan urinib ko‘ring.",
            call.message.chat.id,
            call.message.message_id
        )


# Username qabul qilish
@bot.message_handler(func=lambda message: user_states.get(message.from_user.id, {}).get('step') == 'waiting_username')
def handle_telegram_username(message):
    telegram_username = message.text.strip()

    if not SecurityManager.validate_user_input(telegram_username):
        bot.send_message(message.chat.id, "❌ Noto‘g‘ri username. Qaytadan kiriting:")
        return

    telegram_username = telegram_username.replace('@', '')
    user_state = user_states[message.from_user.id]
    order = user_state['current_order']
    user_state['telegram_username'] = telegram_username
    user_state['step'] = 'waiting_payment'

    payment_info = (
        f"✅ <b>Buyurtma yaratildi!</b>\n\n"
        f"• ⭐ Stars: {order['amount']}\n"
        f"• 💰 Summasi: {order['price']} so‘m\n"
        f"• 👤 Sizning Telegram: @{telegram_username}\n"
        f"• 🎁 Ballar: {order['points']}\n\n"
        f"💳 <b>To‘lov uchun karta:</b>\n"
        f"<code>9860 1266 7183 6719</code>\n\n"
        f"📸 <b>To‘lov qilgandan so‘ng chek (skrinshot) yuboring</b>\n"
        f"⚡ <b>Yetkazib berish:</b> tekshiruvdan so‘ng 1–6 soat ichida"
    )

    bot.send_message(message.chat.id, payment_info, parse_mode='HTML')


# To‘lov skrinshotini qabul qilish
@bot.message_handler(
    content_types=['photo'],
    func=lambda message: user_states.get(message.from_user.id, {}).get('step') == 'waiting_payment'
)
def handle_payment_screenshot(message):
    user_id = message.from_user.id
    user_state = user_states.get(user_id, {})
    order_data = user_state.get('current_order')
    telegram_username = user_state.get('telegram_username')

    try:
        order_info = {
            'user_id': user_id,
            'username': message.from_user.username or '',
            'first_name': message.from_user.first_name or '',
            'telegram_username': telegram_username,
            'stars_amount': order_data['amount'],
            'price': order_data['price'],
            'points': order_data['points'],
        }

        order_id = db.create_order(order_info)

        user_msg = (
            f"📸 <b>Chek qabul qilindi!</b>\n\n"
            f"🆔 <b>Buyurtma raqami:</b> #{order_id}\n"
            f"⏱ <b>Holat:</b> Tekshiruvda\n"
            f"🚚 <b>Yetkazib berish:</b> 1–6 soat\n\n"
            f"Holat o‘zgarganda sizga xabar beramiz."
        )

        bot.send_message(message.chat.id, user_msg, parse_mode='HTML')

        # Foydalanuvchi holatini tozalash
        user_states.pop(user_id, None)

    except Exception as e:
        logger.error(f"Error processing payment: {e}")
        bot.send_message(message.chat.id, "❌ Buyurtmani qayta ishlashda xatolik. Qayta urinib ko‘ring.")
        user_states.pop(user_id, None)


# Profil
@bot.message_handler(func=lambda message: message.text == "👤 Profil")
def show_profile(message):
    user_id = message.from_user.id
    user_data = db.get_user_data(user_id)

    total_spent = user_data.get('total_spent', 0)
    if total_spent >= 5000:
        level = "💎 Platin daraja"
    elif total_spent >= 2000:
        level = "🔥 Oltin daraja"
    elif total_spent >= 500:
        level = "⚡ Kumush daraja"
    else:
        level = "🎯 Bronza daraja"

    profile_text = (
        f"👤 <b>Sizning profilingiz</b>\n\n"
        f"💎 <b>Darajangiz:</b> {level}\n"
        f"⭐ <b>Sotib olingan Stars:</b> {user_data.get('total_stars', 0)}\n"
        f"💰 <b>Jami sarflangan:</b> {user_data.get('total_spent', 0)} so‘m\n"
        f"🎯 <b>To‘plangan ballar:</b> {user_data.get('points', 0)}\n"
        f"📦 <b>Buyurtmalar soni:</b> {user_data.get('orders_count', 0)}\n"
        f"📅 <b>Ro‘yxatdan o‘tgan sana:</b> {user_data.get('registration_date', 'N/A')[:16]}\n\n"
        f"💡 Ballarni to‘plab, bepul Starsga almashtiring!"
    )

    bot.send_message(message.chat.id, profile_text, parse_mode='HTML')


# Yordam
@bot.message_handler(func=lambda message: message.text == "🆘 Yordam")
def show_support(message):
    support_text = (
        f"🆘 <b>Yordam</b>\n\n"
        f"Har qanday savol bo‘yicha murojaat qiling:\n"
        f"👤 {SUPPORT_USERNAME}\n\n"
        f"📞 <b>Biz yordam beramiz:</b>\n"
        f"• Buyurtmalar bo‘yicha savollar\n"
        f"• To‘lov muammolari\n"
        f"• Texnik nosozliklar"
    )
    bot.send_message(message.chat.id, support_text, parse_mode='HTML')


# /help komandasi
@bot.message_handler(commands=['help'])
def help_handler(message):
    help_text = (
        "🤖 <b>Mavjud buyruqlar:</b>\n\n"
        "/start — Botni ishga tushirish\n"
        "/help — Yordam\n"
        "/cancel — Joriy amalni bekor qilish\n\n"
        "📱 <b>Asosiy funksiyalar:</b>\n"
        "• 🛒 Stars sotib olish — Paket tanlash\n"
        "• 👤 Profil — Statistika\n"
        "• 🆘 Yordam — Admin bilan aloqa"
    )
    bot.send_message(message.chat.id, help_text, parse_mode='HTML')


# /cancel komandasi
@bot.message_handler(commands=['cancel'])
def cancel_handler(message):
    user_id = message.from_user.id
    if user_id in user_states:
        user_states.pop(user_id)
        bot.send_message(message.chat.id, "❌ Joriy amal bekor qilindi.")
    else:
        bot.send_message(message.chat.id, "❌ Bekor qilinadigan amal yo‘q.")


# Botni ishga tushirish
if __name__ == "__main__":
    print("🤖 Bot ishga tushmoqda...")
    try:
        bot.infinity_polling()
    except Exception as e:
        logger.error(f"Bot ishlashida xatolik: {e}")
        print(f"❌ Xatolik: {e}")
