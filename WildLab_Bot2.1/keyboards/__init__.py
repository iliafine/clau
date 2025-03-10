# keyboards/__init__.py
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.types import InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton
from aiogram import Bot

def main_menu() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="Заказать консультацию🧠", callback_data="consult")
    builder.button(text="Таблицы🗓", callback_data="tables")
    builder.button(text="Автоответы📨", callback_data="auto_reply")
    builder.button(text="Настройки⚙️", callback_data="settings")
    builder.adjust(1)
    return builder.as_markup()

def tables_menu() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="Расчет себестоимости из Китая🇨🇳", callback_data="china_cost")
    builder.button(text="Проверка цены⚖️", callback_data="price_cost")
    builder.button(text="Главное меню🏠", callback_data="start")
    builder.adjust(1)
    return builder.as_markup()

def subscription_menu() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="Подписаться", url="https://t.me/imwildlab")
    builder.button(text="Я подписался✅", callback_data="check_subscription")
    builder.button(text="На главную🏠", callback_data="start")
    builder.adjust(1)
    return builder.as_markup()

def back_to_menu() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="Главное меню🏠", callback_data="start")
    builder.adjust(1)
    return builder.as_markup()

def back_button() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="◀️ Назад", callback_data="signatures")
    return builder.as_markup()


def settings_menu(user) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()

    if user and user.wb_api_key:
        builder.button(text="❌ Удалить API-ключ", callback_data="delete_api_key")
    else:
        builder.button(text="🔑 Установить API-ключ", callback_data="set_api_key")

    builder.button(text="◀️ На главную", callback_data="start")
    builder.adjust(1)
    return builder.as_markup()

def review_list_keyboard(reviews: list) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for review in reviews:
        builder.button(
            text=f"Отзыв #{review['id']}",
            callback_data=f"review_{review['id']}"
        )

def auto_reply_settings_menu(user) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()


    builder.button(
        text=f"🔔 {'Выключить' if user.notifications_enabled else 'Включить'} уведомления",
        callback_data="toggle_notifications"
    )

    builder.button(text="📝 Настройка подписей", callback_data="signatures")
    builder.button(text=f"⭐ Автоответы на 5★", callback_data="auto_reply_five_stars")
    builder.button(text="◀️ Назад", callback_data="auto_reply")
    builder.adjust(1)

    return builder.as_markup()


def auto_reply_five_stars_menu(user) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()


    builder.button(
        text=f"⭐ {'Выключить' if user.notifications_enabled else 'Включить'} автоответы",
        callback_data="toggle_notifications"
    )

    builder.button(text="◀️ Назад", callback_data="auto_reply")
    builder.adjust(1)

    return builder.as_markup()

def back_button_auto() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="◀️ Назад", callback_data="pending_reviews")

    return builder.as_markup()

def back_button_auto2() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="Настройки⚙️", callback_data="settings")
    builder.button(text="◀️ Назад", callback_data="auto_reply")
    builder.adjust(1)
    return builder.as_markup()

def back_button_auto3() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="◀️ Назад", callback_data="auto_reply")
    builder.adjust(1)
    return builder.as_markup()