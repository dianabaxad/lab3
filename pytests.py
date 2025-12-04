import pytest
import sqlite3
import tempfile
import os
from datetime import date, timedelta
from Main import DeliveryDatabase


@pytest.fixture
def db():
    """Фикстура для создания временной базы данных"""
    # Создаем временный файл БД для тестов
    with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as tmp:
        db_path = tmp.name

    # Создаем экземпляр базы данных
    db_instance = DeliveryDatabase(db_path)

    yield db_instance

    # Очистка после теста
    if os.path.exists(db_path):
        os.remove(db_path)

    # Удаляем файл логов если он создался
    log_file = 'delivery_activity.log'
    if os.path.exists(log_file):
        os.remove(log_file)

        def test_add_order_valid(db):
            """Тест добавления валидного заказа"""
            order_id = db.add_order("Иван", "Молоко", 2, 50.0, "2025-12-03")

            assert isinstance(order_id, int)
            assert order_id > 0

            orders = db.get_all_orders()
            assert len(orders) == 1

            order = orders[0]
            assert order[1] == "Иван"  # customer_name
            assert order[2] == "Молоко"  # product
            assert order[3] == 2  # quantity
            assert order[4] == 50.0  # price
            assert order[5] == "2025-12-03"  # delivery_date
            assert order[6] == "в обработке"  # status