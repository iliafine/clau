# utils/prompts.py
from models import UserSettings
def build_prompt(review: dict, user: UserSettings, arguments: list, solution: str = None) -> str:
    sections = [
        "Напиши ответ на отзыв с содержанием:",
        f"Отзыв: {review['comment']}",
        f"Достоинства: {review.get('pros', 'не указаны')}",
        f"Недостатки: {review.get('cons', 'не указаны')}"
    ]

    if user.greeting:
        sections.append(f"Используй приветствие: {user.greeting}")
    if user.farewell:
        sections.append(f"Используй прощание: {user.farewell}")
    if arguments:
        sections.append(f"Используй аргументы: {', '.join(arguments)}")
    if solution:
        sections.append(f"Предложи решение: {solution}")

    sections.append("\n<!-- TEST PROMPT v1.0 -->")
    return "\n".join(sections)