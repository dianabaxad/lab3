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


def test_add_order_invalid_quantity(db):
    """Тест добавления заказа с невалидным количеством (отрицательное)"""
    # SQLite не проверяет отрицательные значения автоматически
    # Проверяем, что заказ все равно добавляется
    order_id = db.add_order("Иван", "Молоко", -1, 50.0, "2025-12-03")

    # Проверяем, что заказ был добавлен
    orders = db.get_all_orders()
    assert len(orders) == 1
    assert orders[0][3] == -1  # отрицательное количество


def test_delete_order(db):
    """Тест удаления заказа"""
    order_id = db.add_order("Иван", "Хлеб", 1, 30.0, "2025-12-03")

    # Проверяем, что заказ добавлен
    orders_before = db.get_all_orders()
    assert len(orders_before) == 1

    # Удаляем заказ
    db.delete_order(order_id)

    # Проверяем, что заказ удален
    orders_after = db.get_all_orders()
    assert len(orders_after) == 0


def test_get_revenue_stats(db):
    """Тест получения статистики выручки"""
    today = date.today()

    # Добавляем заказы на разные даты
    for i in range(5):
        day = today + timedelta(days=i)
        db.add_order(f"Клиент{i}", f"Продукт{i}", 1, 100.0, day.isoformat())

    # Получаем статистику за 7 дней
    stats = db.get_revenue_stats(7)

    # Проверяем, что статистика получена
    assert isinstance(stats, list)
    assert len(stats) >= 5  # Может быть больше, если есть другие дни с данными

    # Проверяем структуру данных
    for stat in stats:
        assert len(stat) == 2  # дата и выручка
        assert isinstance(stat[0], str)  # дата - строка
        # Выручка может быть float или int
        assert isinstance(stat[1], (float, int))


def test_general_statistics(db):
    """Тест получения общей статистики"""
    # Добавляем два заказа
    db.add_order("Иван", "Молоко", 2, 50.0, "2025-12-03")
    db.add_order("Петр", "Хлеб", 1, 30.0, "2025-12-03")

    # Получаем статистику
    stats = db.get_general_statistics()

    # Проверяем результаты
    assert stats['total_orders'] == 2
    assert stats['total_revenue'] == 130.0  # 2*50 + 1*30
    assert stats['average_order_value'] == 65.0  # 130 / 2


def test_activity_table_updates(db):
    """Тест обновления таблицы активности"""
    # Добавляем два заказа на одну дату
    db.add_order("А", "Товар1", 1, 100.0, "2025-12-03")
    db.add_order("Б", "Товар2", 2, 50.0, "2025-12-03")

    # Проверяем обновление таблицы activity
    conn = sqlite3.connect(db.db_name)
    cursor = conn.cursor()
    cursor.execute("SELECT orders_count, revenue FROM activity WHERE date = ?", ("2025-12-03",))
    record = cursor.fetchone()
    conn.close()

    assert record is not None
    assert record[0] == 2  # количество заказов
    assert record[1] == 200.0  # выручка: 100 + (2*50)


def test_get_all_orders_empty(db):
    """Тест получения заказов из пустой БД"""
    orders = db.get_all_orders()

    assert isinstance(orders, list)
    assert len(orders) == 0


def test_get_all_orders_sorting(db):
    """Тест сортировки заказов по дате"""
    # Добавляем заказы в разном порядке
    db.add_order("Клиент1", "Товар1", 1, 10.0, "2025-12-01")
    db.add_order("Клиент2", "Товар2", 2, 20.0, "2025-12-03")
    db.add_order("Клиент3", "Товар3", 3, 30.0, "2025-12-02")

    orders = db.get_all_orders()

    # Проверяем сортировку по убыванию даты
    assert len(orders) == 3
    assert orders[0][5] == "2025-12-03"  # Самая поздняя дата первая
    assert orders[1][5] == "2025-12-02"
    assert orders[2][5] == "2025-12-01"  # Самая ранняя дата последняя


def test_delete_nonexistent_order(db):
    """Тест удаления несуществующего заказа"""
    # Удаление несуществующего заказа не должно вызывать ошибку
    db.delete_order(999)

    # Проверяем, что БД все еще работает
    orders = db.get_all_orders()
    assert orders == []


def test_multiple_orders_same_customer(db):
    """Тест нескольких заказов от одного клиента"""
    db.add_order("Иван", "Молоко", 2, 50.0, "2025-12-03")
    db.add_order("Иван", "Хлеб", 1, 30.0, "2025-12-04")
    db.add_order("Иван", "Сыр", 3, 100.0, "2025-12-05")

    orders = db.get_all_orders()

    assert len(orders) == 3
    # Проверяем, что все заказы от Ивана
    for order in orders:
        assert order[1] == "Иван"


def test_revenue_stats_different_dates(db):
    """Тест статистики выручки на разные даты"""
    # Добавляем заказы на разные даты
    db.add_order("Клиент1", "Товар1", 2, 100.0, "2025-12-01")
    db.add_order("Клиент2", "Товар2", 1, 50.0, "2025-12-02")
    db.add_order("Клиент3", "Товар3", 3, 30.0, "2025-12-03")

    stats = db.get_revenue_stats(10)

    # Должно быть 3 записи (по одной на каждый день)
    assert len(stats) >= 3

    # Ищем наши даты в статистике
    dates = [stat[0] for stat in stats]
    assert "2025-12-01" in dates
    assert "2025-12-02" in dates
    assert "2025-12-03" in dates


def test_database_initialization():
    """Тест инициализации базы данных"""
    # Создаем временный файл БД
    with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as tmp:
        db_path = tmp.name

    try:
        # Создаем экземпляр базы данных
        db = DeliveryDatabase(db_path)

        # Проверяем, что файл создан
        assert os.path.exists(db_path)
        assert db.db_name == db_path

        # Проверяем, что таблицы созданы
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = [table[0] for table in cursor.fetchall()]

        assert 'orders' in tables
        assert 'activity' in tables

        # Проверяем структуру таблицы orders
        cursor.execute("PRAGMA table_info(orders)")
        orders_columns = cursor.fetchall()
        assert len(orders_columns) == 7  # 7 полей

        # Проверяем структуру таблицы activity
        cursor.execute("PRAGMA table_info(activity)")
        activity_columns = cursor.fetchall()
        assert len(activity_columns) == 4  # 4 поля

        conn.close()

    finally:
        # Очистка
        if os.path.exists(db_path):
            os.remove(db_path)
