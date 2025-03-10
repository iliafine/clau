from aiogram.utils.keyboard import InlineKeyboardBuilder


def paginate_reviews(reviews: list, page: int, page_size: int = 5) -> dict:
    """
    Пагинация списка отзывов.

    Args:
        reviews (list): Список отзывов.
        page (int): Текущая страница.
        page_size (int): Количество отзывов на странице.

    Returns:
        dict: Словарь с отзывами и клавиатурой пагинации.
    """
    for review in reviews:
        review['photo'] = 'Да' if review.get('photo') == 'True' else 'Нет'
    # Проверка входных данных
    if not isinstance(reviews, list):
        raise ValueError("reviews должен быть списком")

    if not isinstance(page, int) or page < 0:
        raise ValueError("page должен быть неотрицательным целым числом")

    if not isinstance(page_size, int) or page_size <= 0:
        raise ValueError("page_size должен быть положительным целым числом")

    # Если список отзывов пуст, возвращаем пустой результат
    if not reviews:
        return {
            "reviews": [],
            "keyboard": None
        }

    # Вычисляем общее количество страниц
    total = len(reviews)
    pages = (total + page_size - 1) // page_size

    # Корректируем текущую страницу, если она выходит за пределы
    if page >= pages:
        page = pages - 1

    # Вычисляем индексы для среза
    start_idx = page * page_size
    end_idx = start_idx + page_size

    # Создаем клавиатуру для отзывов
    reviews_builder = InlineKeyboardBuilder()
    for review in reviews[start_idx:end_idx]:
        # Проверяем, что review — это словарь и содержит необходимые поля
        if not isinstance(review, dict):
            continue

        review_id = review.get("id")
        stars = review.get("stars", 0)
        comment = review.get("comment", "")
        has_photo = review.get("photo", False)

        # Формируем текст кнопки
        review_text = f"{stars}⭐ | {'📸' if has_photo else ''} {comment[:20]}..."
        reviews_builder.button(
            text=review_text,
            callback_data=f"review_{review_id}"
        )

    # Создаем клавиатуру для пагинации
    pagination_builder = InlineKeyboardBuilder()
    if page > 0:
        pagination_builder.button(text="◀️", callback_data=f"page_{page - 1}")
    pagination_builder.button(text=f"{page + 1}/{pages}", callback_data="current")
    if page < pages - 1:
        pagination_builder.button(text="▶️", callback_data=f"page_{page + 1}")

    # Возвращаем результат
    return {
        "reviews": reviews[start_idx:end_idx],
        "keyboard": pagination_builder.as_markup()
    }