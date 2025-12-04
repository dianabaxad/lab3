import sys
import sqlite3
import logging
from datetime import datetime, date
from typing import List, Tuple
import os

from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QTableWidget, QTableWidgetItem, QLabel, QLineEdit, QPushButton,
    QMessageBox, QMenuBar, QMenu, QFormLayout, QGroupBox, QStatusBar,
    QDateEdit, QSplitter
)
from PySide6.QtCore import Qt, QDate
from PySide6.QtGui import QAction
import matplotlib.pyplot as plt
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas


# Кастомные исключения
class DeliveryAppError(Exception):
    """Базовое исключение для приложения доставки"""
    pass


class InvalidDataError(DeliveryAppError):
    """Исключение для невалидных данных"""
    pass


class DatabaseError(DeliveryAppError):
    """Исключение для ошибок базы данных"""
    pass


# Класс для работы с базой данных
class DeliveryDatabase:
    def __init__(self, db_name: str = "delivery.db"):
        self.db_name = db_name
        self._setup_logging()
        self._validate_db_exists()
        self._check_and_create_tables()

    def _validate_db_exists(self):
        """Проверяем, существует ли файл базы данных"""
        if not os.path.exists(self.db_name):
            # Создаем пустую базу данных
            conn = sqlite3.connect(self.db_name)
            conn.close()
            logging.info(f"Создана новая база данных: {self.db_name}")

    def _check_and_create_tables(self):
        """Проверяем и создаем необходимые таблицы"""
        try:
            conn = sqlite3.connect(self.db_name)
            cursor = conn.cursor()

            # Проверяем существование таблицы orders
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='orders'")
            if not cursor.fetchone():
                cursor.execute('''
                    CREATE TABLE orders (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        customer_name TEXT NOT NULL,
                        product TEXT NOT NULL,
                        quantity INTEGER NOT NULL,
                        price REAL NOT NULL,
                        delivery_date DATE NOT NULL,
                        status TEXT DEFAULT 'в обработке'
                    )
                ''')
                logging.info("Создана таблица 'orders'")

            # Проверяем существование таблицы activity
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='activity'")
            if not cursor.fetchone():
                cursor.execute('''
                    CREATE TABLE activity (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        date DATE UNIQUE NOT NULL,
                        orders_count INTEGER DEFAULT 0,
                        revenue REAL DEFAULT 0
                    )
                ''')
                logging.info("Создана таблица 'activity'")

            conn.commit()
            conn.close()

        except sqlite3.Error as e:
            raise DatabaseError(f"Ошибка при проверке/создании таблиц: {e}")

    def _setup_logging(self):
        """Настройка логирования"""
        logging.basicConfig(
            filename='delivery_activity.log',
            level=logging.INFO,
            format='%(asctime)s - %(levelname)s - %(message)s',
            encoding='utf-8'
        )
        logging.info(f"Инициализация базы данных: {self.db_name}")

    def add_order(self, customer: str, product: str, quantity: int, price: float, delivery_date: str) -> int:
        """Добавление нового заказа"""
        try:
            conn = sqlite3.connect(self.db_name)
            cursor = conn.cursor()

            # Добавляем заказ
            cursor.execute('''
                INSERT INTO orders (customer_name, product, quantity, price, delivery_date, status)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (customer, product, quantity, price, delivery_date, 'в обработке'))

            order_id = cursor.lastrowid

            # Рассчитываем общую сумму заказа
            total_amount = price * quantity

            # Обновляем статистику активности для даты доставки (а не сегодняшней даты)
            cursor.execute("SELECT id FROM activity WHERE date = ?", (delivery_date,))
            existing_record = cursor.fetchone()

            if existing_record:
                # Обновляем существующую запись
                cursor.execute('''
                    UPDATE activity 
                    SET orders_count = orders_count + 1,
                        revenue = revenue + ?
                    WHERE date = ?
                ''', (total_amount, delivery_date))
            else:
                # Создаем новую запись
                cursor.execute('''
                    INSERT INTO activity (date, orders_count, revenue)
                    VALUES (?, 1, ?)
                ''', (delivery_date, total_amount))

            conn.commit()
            conn.close()

            logging.info(f"Добавлен новый заказ №{order_id} от {customer} на сумму {total_amount} руб.")
            return order_id

        except sqlite3.Error as e:
            raise DatabaseError(f"Ошибка добавления заказа: {e}")
        finally:
            if 'conn' in locals():
                conn.close()

    def get_all_orders(self) -> List[Tuple]:
        """Получение всех заказов"""
        try:
            conn = sqlite3.connect(self.db_name)
            cursor = conn.cursor()

            # Получаем заказы
            cursor.execute('SELECT * FROM orders ORDER BY delivery_date DESC')
            orders = cursor.fetchall()
            conn.close()
            return orders
        except sqlite3.Error as e:
            raise DatabaseError(f"Ошибка получения заказов: {e}")
        finally:
            if 'conn' in locals():
                conn.close()

    def get_revenue_stats(self, days: int = 30) -> List[Tuple]:
        """Получение статистики выручки по дням"""
        try:
            conn = sqlite3.connect(self.db_name)
            cursor = conn.cursor()

            # Получаем статистику выручки за указанное количество дней
            # Если нет записей в activity, вычисляем из orders
            cursor.execute('''
                SELECT date, revenue 
                FROM activity 
                WHERE date >= date('now', ?)
                ORDER BY date ASC
            ''', (f'-{days} days',))

            stats = cursor.fetchall()

            # Если в activity нет данных, вычисляем из orders
            if not stats:
                cursor.execute('''
                    SELECT 
                        delivery_date as date,
                        SUM(price * quantity) as revenue
                    FROM orders 
                    WHERE delivery_date >= date('now', ?)
                    GROUP BY delivery_date
                    ORDER BY delivery_date ASC
                ''', (f'-{days} days',))

                stats = cursor.fetchall()

            conn.close()
            return stats
        except sqlite3.Error as e:
            logging.warning(f"Ошибка получения статистики выручки: {e}")
            return []
        finally:
            if 'conn' in locals():
                conn.close()

    def delete_order(self, order_id: int):
        """Удаление заказа"""
        try:
            conn = sqlite3.connect(self.db_name)
            cursor = conn.cursor()

            # Получаем данные заказа перед удалением
            cursor.execute('SELECT price, quantity, delivery_date FROM orders WHERE id = ?', (order_id,))
            order = cursor.fetchone()

            if order:
                price, quantity, order_date = order
                revenue = price * quantity

                # Форматируем дату
                try:
                    if isinstance(order_date, str):
                        if ' ' in order_date:
                            order_date_only = order_date.split(' ')[0]
                        else:
                            order_date_only = order_date
                    else:
                        order_date_only = order_date

                    # Обновляем статистику
                    cursor.execute("SELECT id FROM activity WHERE date = ?", (order_date_only,))
                    existing_record = cursor.fetchone()

                    if existing_record:
                        cursor.execute('''
                            UPDATE activity 
                            SET orders_count = orders_count - 1,
                                revenue = revenue - ?
                            WHERE date = ?
                        ''', (revenue, order_date_only))

                except Exception as e:
                    logging.warning(f"Ошибка при обновлении статистики: {e}")

            # Удаляем заказ
            cursor.execute('DELETE FROM orders WHERE id = ?', (order_id,))
            conn.commit()
            conn.close()

            logging.info(f"Удален заказ №{order_id}")

        except sqlite3.Error as e:
            raise DatabaseError(f"Ошибка удаления заказа: {e}")
        finally:
            if 'conn' in locals():
                conn.close()

    def get_general_statistics(self) -> dict:
        """Получение общей статистики"""
        try:
            conn = sqlite3.connect(self.db_name)
            cursor = conn.cursor()

            # Получаем общую выручку и количество заказов
            cursor.execute('''
                SELECT 
                    COUNT(*) as total_orders,
                    SUM(price * quantity) as total_revenue
                FROM orders
            ''')

            result = cursor.fetchone()

            total_orders = result[0] if result and result[0] else 0
            total_revenue = result[1] if result and result[1] else 0.0

            # Вычисляем среднюю стоимость заказа
            average_order_value = total_revenue / total_orders if total_orders > 0 else 0.0

            conn.close()

            return {
                'total_orders': total_orders,
                'total_revenue': total_revenue,
                'average_order_value': average_order_value
            }

        except sqlite3.Error as e:
            logging.warning(f"Ошибка получения общей статистики: {e}")
            return {
                'total_orders': 0,
                'total_revenue': 0.0,
                'average_order_value': 0.0
            }
        finally:
            if 'conn' in locals():
                conn.close()

# Виджет для отображения графика - дата и выручка
class RevenueGraph(QWidget):
    def __init__(self):
        super().__init__()
        self.figure, self.ax = plt.subplots(figsize=(8, 4))
        self.canvas = FigureCanvas(self.figure)
        self.init_ui()