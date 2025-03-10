# db_migration.py
import sqlite3
import logging

# Настраиваем логирование
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def migrate_database():
    """
    Добавляет новые колонки в таблицу reviews
    """
    try:
        # Подключаемся к базе данных
        conn = sqlite3.connect('bot.db')
        cursor = conn.cursor()

        # Получаем текущие колонки
        cursor.execute("PRAGMA table_info(reviews)")
        columns = cursor.fetchall()
        column_names = [column[1] for column in columns]

        # Список колонок для добавления и их типы
        new_columns = {
            'photo_urls': 'TEXT',
            'product_name': 'TEXT',
            'product_id': 'TEXT',
            'supplier_article': 'TEXT',
            'subject_name': 'TEXT'  # Добавляем новое поле
        }

        # Добавляем отсутствующие колонки
        for column_name, column_type in new_columns.items():
            if column_name not in column_names:
                logger.info(f"Adding column {column_name} to reviews table")
                cursor.execute(f"ALTER TABLE reviews ADD COLUMN {column_name} {column_type}")

                # Инициализируем колонку значениями по умолчанию
                default_value = "'[]'" if column_name == 'photo_urls' else "''"
                cursor.execute(f"UPDATE reviews SET {column_name} = {default_value}")

                logger.info(f"Successfully added column {column_name}")

        # Сохраняем изменения
        conn.commit()
        logger.info("Database migration completed")

        # Закрываем соединение
        conn.close()
        return True

    except Exception as e:
        logger.error(f"Database migration error: {str(e)}", exc_info=True)
        return False


if __name__ == "__main__":
    result = migrate_database()
    if result:
        print("Migration completed successfully")
    else:
        print("Migration failed")