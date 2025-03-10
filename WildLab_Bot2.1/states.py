# states.py
from aiogram.fsm.state import StatesGroup, State

class SettingsState(StatesGroup):
    waiting_api_key = State()
    waiting_greeting = State()
    waiting_farewell = State()
    waiting_arguments = State()

class AutoReplyState(StatesGroup):
    waiting_arguments = State()
    waiting_custom_reply = State()
    confirmation = State()
    waiting_greeting = State()
    waiting_farewell = State()
    waiting_signature = State()

class ReviewState(StatesGroup):
    waiting_for_review_selection = State()
    waiting_for_arguments = State()
    waiting_for_send_confirmation = State()
    waiting_for_action = State()
    waiting_for_custom_reply = State()
    waiting_for_solution = State()