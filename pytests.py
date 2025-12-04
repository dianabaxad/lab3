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