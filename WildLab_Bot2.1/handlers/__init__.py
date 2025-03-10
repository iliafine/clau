# handlers/__init__.py
from .auto_reply import router as auto_reply_router
from .settings import router as settings_router
from aiogram import Bot

__all__ = [
    'auto_reply_router',
    'settings_router'
]