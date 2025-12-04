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

    def init_ui(self):
        layout = QVBoxLayout()
        layout.addWidget(self.canvas)
        self.setLayout(layout)

    def update_graph(self, stats: List[Tuple]):
        """Обновление графика выручки"""
        self.ax.clear()

        if stats:
            dates = [stat[0] for stat in stats]
            revenue = [stat[1] for stat in stats]

            # Создаем линейный график выручки
            self.ax.plot(dates, revenue, 'g-o', linewidth=2, markersize=5)

            # Настройки графика
            self.ax.set_xlabel('Дата')
            self.ax.set_ylabel('Выручка (руб)', color='g')
            self.ax.tick_params(axis='y', labelcolor='g')
            self.ax.grid(True, alpha=0.3)

            self.ax.set_title('Выручка по дням (последние 30 дней)')
            self.ax.tick_params(axis='x', rotation=45)

            # Форматируем значения на оси Y как денежные
            self.ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda x, p: f'{x:,.0f} руб'))

            self.figure.tight_layout()
        else:
            # Отображаем сообщение, если нет данных
            self.ax.text(0.5, 0.5, 'Нет данных для отображения\nДобавьте первый заказ',
                         horizontalalignment='center', verticalalignment='center',
                         transform=self.ax.transAxes, fontsize=12)
            self.ax.set_title('Выручка по дням')
            self.ax.set_xticks([])
            self.ax.set_yticks([])

        self.canvas.draw()


# Главное окно приложения
class DeliveryApp(QMainWindow):
    def __init__(self):
        super().__init__()
        try:
            self.db = DeliveryDatabase()
            self.init_ui()
            self.load_orders()
            self.update_graph()
            self.update_general_statistics()
        except DatabaseError as e:
            QMessageBox.critical(self, "Ошибка базы данных", str(e))
            sys.exit(1)
        except Exception as e:
            QMessageBox.critical(self, "Критическая ошибка", f"Не удалось запустить приложение: {str(e)}")
            sys.exit(1)

    def init_ui(self):
        """Инициализация пользоватерского интерфейса"""
        self.setWindowTitle("Сервис доставки продуктов")
        self.setGeometry(100, 100, 1200, 700)

        # Создаем центральный виджет
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)

        # Создаем меню
        self.create_menu()

        # Верхняя часть: форма ввода данных
        input_group = QGroupBox("Добавить новый заказ")
        form_layout = QFormLayout()

        self.customer_input = QLineEdit()
        self.customer_input.setPlaceholderText("Имя клиента")
        self.customer_input.setMinimumWidth(200)
        form_layout.addRow("Клиент:", self.customer_input)

        self.product_input = QLineEdit()
        self.product_input.setPlaceholderText("Название продукта")
        self.product_input.setMinimumWidth(200)
        form_layout.addRow("Продукт:", self.product_input)

        self.quantity_input = QLineEdit()
        self.quantity_input.setPlaceholderText("Количество")
        self.quantity_input.setMinimumWidth(100)
        form_layout.addRow("Количество:", self.quantity_input)

        self.price_input = QLineEdit()
        self.price_input.setPlaceholderText("Цена за единицу")
        self.price_input.setMinimumWidth(100)
        form_layout.addRow("Цена:", self.price_input)

        # Календарь для выбора даты
        self.date_input = QDateEdit()
        self.date_input.setDate(QDate.currentDate())
        self.date_input.setCalendarPopup(True)  # Включаем выпадающий календарь
        self.date_input.setDisplayFormat("yyyy-MM-dd")
        self.date_input.setMinimumWidth(120)
        form_layout.addRow("Дата доставки:", self.date_input)

        # Кнопки
        button_layout = QHBoxLayout()
        add_button = QPushButton("Добавить заказ")
        add_button.clicked.connect(self.add_order)

        clear_button = QPushButton("Очистить форму")
        clear_button.clicked.connect(self.clear_form)

        button_layout.addWidget(add_button)
        button_layout.addWidget(clear_button)
        form_layout.addRow(button_layout)

        input_group.setLayout(form_layout)
        main_layout.addWidget(input_group)

        # Средняя часть: таблица и график
        middle_splitter = QSplitter(Qt.Horizontal)

        # Таблица заказов
        table_group = QGroupBox("Текущие заказы")
        table_layout = QVBoxLayout()
        self.table = QTableWidget()
        self.table.setColumnCount(7)
        self.table.setHorizontalHeaderLabels([
            "ID", "Клиент", "Продукт", "Кол-во", "Цена", "Дата доставки", "Статус"
        ])
        self.table.setSortingEnabled(True)
        self.table.setAlternatingRowColors(True)

        delete_button = QPushButton("Удалить выбранный заказ")
        delete_button.clicked.connect(self.delete_selected_order)

        refresh_button = QPushButton("Обновить таблицу")
        refresh_button.clicked.connect(self.load_orders)

        table_layout.addWidget(self.table)

        button_layout2 = QHBoxLayout()
        button_layout2.addWidget(delete_button)
        button_layout2.addWidget(refresh_button)
        table_layout.addLayout(button_layout2)

        table_group.setLayout(table_layout)

        middle_splitter.addWidget(table_group)

        # График выручки
        graph_group = QGroupBox("График выручки")
        graph_layout = QVBoxLayout()
        self.graph_widget = RevenueGraph()
        graph_layout.addWidget(self.graph_widget)
        graph_group.setLayout(graph_layout)

        middle_splitter.addWidget(graph_group)

        # Устанавливаем пропорции разделителя
        middle_splitter.setSizes([700, 500])

        main_layout.addWidget(middle_splitter)

        # Нижняя панель: общая статистика
        stats_group = QGroupBox("Общая статистика")
        stats_layout = QVBoxLayout()

        # Контейнер для меток статистики
        stats_container = QWidget()
        stats_container_layout = QHBoxLayout(stats_container)

        # Метки для статистики
        self.total_revenue_label = QLabel("Общая выручка: 0 руб")
        self.total_revenue_label.setAlignment(Qt.AlignCenter)
        self.total_revenue_label.setStyleSheet("font-weight: bold; font-size: 14px; padding: 10px;")

        self.total_orders_label = QLabel("Общее количество заказов: 0")
        self.total_orders_label.setAlignment(Qt.AlignCenter)
        self.total_orders_label.setStyleSheet("font-weight: bold; font-size: 14px; padding: 10px;")

        self.average_order_label = QLabel("Средняя стоимость заказа: 0 руб")
        self.average_order_label.setAlignment(Qt.AlignCenter)
        self.average_order_label.setStyleSheet("font-weight: bold; font-size: 14px; padding: 10px;")

        # Добавляем метки в контейнер
        stats_container_layout.addWidget(self.total_revenue_label)
        stats_container_layout.addWidget(self.total_orders_label)
        stats_container_layout.addWidget(self.average_order_label)

        stats_layout.addWidget(stats_container)
        stats_group.setLayout(stats_layout)

        main_layout.addWidget(stats_group)

        # Статус бар
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        self.status_bar.showMessage("Готово")

    def create_menu(self):
        """Создание меню приложения"""
        menubar = self.menuBar()

        # Меню Файл
        file_menu = menubar.addMenu("Файл")

        refresh_action = QAction("Обновить всё", self)
        refresh_action.triggered.connect(self.refresh_all)
        file_menu.addAction(refresh_action)

        export_action = QAction("Экспорт логов", self)
        export_action.triggered.connect(self.export_logs)
        file_menu.addAction(export_action)

        file_menu.addSeparator()

        exit_action = QAction("Выход", self)
        exit_action.triggered.connect(self.close)
        file_menu.addAction(exit_action)

        # Меню График
        graph_menu = menubar.addMenu("График")

        days_7_action = QAction("Последние 7 дней", self)
        days_7_action.triggered.connect(lambda: self.update_graph_with_days(7))
        graph_menu.addAction(days_7_action)

        days_30_action = QAction("Последние 30 дней", self)
        days_30_action.triggered.connect(lambda: self.update_graph_with_days(30))
        graph_menu.addAction(days_30_action)

        days_90_action = QAction("Последние 90 дней", self)
        days_90_action.triggered.connect(lambda: self.update_graph_with_days(90))
        graph_menu.addAction(days_90_action)

        # Меню Помощь
        help_menu = menubar.addMenu("Помощь")

        about_action = QAction("О программе", self)
        about_action.triggered.connect(self.show_about)
        help_menu.addAction(about_action)

    def update_general_statistics(self):
        """Обновление отображения общей статистики"""
        try:
            stats = self.db.get_general_statistics()

            # Форматируем значения
            total_revenue_formatted = f"{stats['total_revenue']:,.2f} руб"
            average_order_formatted = f"{stats['average_order_value']:,.2f} руб"

            # Обновляем метки
            self.total_revenue_label.setText(f"Общая выручка: {total_revenue_formatted}")
            self.total_orders_label.setText(f"Общее количество заказов: {stats['total_orders']}")
            self.average_order_label.setText(f"Средняя стоимость заказа: {average_order_formatted}")

        except Exception as e:
            logging.error(f"Ошибка обновления общей статистики: {e}")

    def update_graph_with_days(self, days: int):
        """Обновление графика за указанное количество дней"""
        try:
            stats = self.db.get_revenue_stats(days)
            self.graph_widget.update_graph(stats)
            self.status_bar.showMessage(f"График обновлен: последние {days} дней", 3000)
        except Exception as e:
            logging.error(f"Ошибка обновления графика: {e}")

    def clear_form(self):
        """Очистка формы ввода"""
        self.customer_input.clear()
        self.product_input.clear()
        self.quantity_input.clear()
        self.price_input.clear()
        self.date_input.setDate(QDate.currentDate())
        self.status_bar.showMessage("Форма очищена", 2000)

    def refresh_all(self):
        """Обновить все данные"""
        self.load_orders()
        self.update_graph()
        self.update_general_statistics()
        self.status_bar.showMessage("Все данные обновлены", 2000)

    def validate_input(self) -> tuple:
        """Валидация введенных данных"""
        try:
            customer = self.customer_input.text().strip()
            product = self.product_input.text().strip()
            quantity_text = self.quantity_input.text().strip()
            price_text = self.price_input.text().strip()
            date_text = self.date_input.date().toString("yyyy-MM-dd")

            if not customer:
                raise InvalidDataError("Введите имя клиента")
            if not product:
                raise InvalidDataError("Введите название продукта")

            try:
                quantity = int(quantity_text)
                if quantity <= 0:
                    raise InvalidDataError("Количество должно быть положительным числом")
            except ValueError:
                raise InvalidDataError("Количество должно быть целым числом")

            try:
                price = float(price_text)
                if price <= 0:
                    raise InvalidDataError("Цена должна быть положительным числом")
            except ValueError:
                raise InvalidDataError("Цена должна быть числом")

            # Проверка даты
            try:
                datetime.strptime(date_text, "%Y-%m-%d")
            except ValueError:
                raise InvalidDataError("Дата должна быть в формате ГГГГ-ММ-ДД")

            return customer, product, quantity, price, date_text

        except InvalidDataError as e:
            raise
        except Exception as e:
            raise InvalidDataError(f"Ошибка валидации: {str(e)}")

    def add_order(self):
        """Добавление нового заказа"""
        try:
            customer, product, quantity, price, delivery_date = self.validate_input()

            order_id = self.db.add_order(customer, product, quantity, price, delivery_date)

            total_amount = price * quantity
            QMessageBox.information(self, "Успех",
                                    f"Заказ №{order_id} успешно добавлен!\n"
                                    f"Сумма заказа: {total_amount:.2f} руб")

            # Очистка полей ввода
            self.clear_form()

            # Обновление данных
            self.refresh_all()
            self.status_bar.showMessage(f"Добавлен заказ №{order_id} на сумму {total_amount:.2f} руб", 3000)

        except InvalidDataError as e:
            QMessageBox.warning(self, "Ошибка ввода", str(e))
            logging.warning(f"Ошибка ввода данных: {e}")
        except DatabaseError as e:
            QMessageBox.critical(self, "Ошибка БД", str(e))
            logging.error(f"Ошибка базы данных: {e}")
        except Exception as e:
            QMessageBox.critical(self, "Ошибка", f"Неизвестная ошибка: {str(e)}")
            logging.error(f"Неизвестная ошибка: {e}")

    def load_orders(self):
        """Загрузка заказов в таблицу"""
        try:
            orders = self.db.get_all_orders()
            self.table.setRowCount(len(orders))

            for row, order in enumerate(orders):
                for col, value in enumerate(order):
                    item = QTableWidgetItem(str(value) if value is not None else "")
                    item.setFlags(item.flags() & ~Qt.ItemIsEditable)

                    # Выравнивание числовых полей по правому краю
                    if col in [3, 4]:  # Колонки с количеством и ценой
                        item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)

                    self.table.setItem(row, col, item)

            self.table.resizeColumnsToContents()
            self.status_bar.showMessage(f"Загружено {len(orders)} заказов", 3000)

        except DatabaseError as e:
            QMessageBox.critical(self, "Ошибка БД", str(e))
            logging.error(f"Ошибка загрузки заказов: {e}")
        except Exception as e:
            QMessageBox.critical(self, "Ошибка", f"Ошибка при загрузке заказов: {str(e)}")
            logging.error(f"Ошибка при загрузке заказов: {e}")

    def update_graph(self):
        """Обновление графика выручки"""
        try:
            stats = self.db.get_revenue_stats(30)  # По умолчанию последние 30 дней
            self.graph_widget.update_graph(stats)
        except Exception as e:
            logging.error(f"Ошибка обновления графика: {e}")

    def delete_selected_order(self):
        """Удаление выбранного заказа"""
        selected_rows = set()
        for item in self.table.selectedItems():
            selected_rows.add(item.row())

        if not selected_rows:
            QMessageBox.warning(self, "Внимание", "Выберите заказ для удаления")
            return

        row = list(selected_rows)[0]
        order_id_item = self.table.item(row, 0)

        if order_id_item and order_id_item.text():
            try:
                order_id = int(order_id_item.text())
                customer = self.table.item(row, 1).text()
                product = self.table.item(row, 2).text()

                reply = QMessageBox.question(
                    self, "Подтверждение",
                    f"Удалить заказ №{order_id}?\nКлиент: {customer}\nПродукт: {product}",
                    QMessageBox.Yes | QMessageBox.No
                )

                if reply == QMessageBox.Yes:
                    self.db.delete_order(order_id)
                    self.refresh_all()
                    self.status_bar.showMessage(f"Удален заказ №{order_id}", 3000)
            except ValueError:
                QMessageBox.warning(self, "Ошибка", "Неверный ID заказа")
            except DatabaseError as e:
                QMessageBox.critical(self, "Ошибка БД", str(e))
                logging.error(f"Ошибка удаления заказа: {e}")

    def export_logs(self):
        """Экспорт логов"""
        try:
            log_file = 'delivery_activity.log'
            if not os.path.exists(log_file):
                QMessageBox.warning(self, "Внимание", "Файл логов не найден")
                return

            with open(log_file, 'r', encoding='utf-8') as f:
                logs = f.read()

            export_file = f'delivery_logs_export_{datetime.now().strftime("%Y%m%d_%H%M%S")}.txt'
            with open(export_file, 'w', encoding='utf-8') as f:
                f.write(logs)

            QMessageBox.information(self, "Успех", f"Логи успешно экспортированы в {export_file}")
            logging.info(f"Логи экспортированы в {export_file}")

        except Exception as e:
            QMessageBox.critical(self, "Ошибка", f"Ошибка экспорта логов: {str(e)}")
            logging.error(f"Ошибка экспорта логов: {e}")

    def show_about(self):
        """Показать информацию о программе"""
        about_text = """
        <h2>Сервис доставки продуктов</h2>
        <p>Версия 1.2</p>
        <p>Приложение для управления заказами доставки продуктов.</p>
        <p>Функции:</p>
        <ul>
            <li>Добавление и удаление заказов</li>
            <li>Просмотр статистики в таблице</li>
            <li>График выручки по дням</li>
            <li>Общая статистика: выручка, количество заказов, средняя стоимость</li>
            <li>Логирование всех действий</li>
        </ul>
        <p>График показывает выручку (доход) по дням.</p>
        <p>Все данные хранятся в локальной базе SQLite.</p>
        """
        QMessageBox.about(self, "О программе", about_text)


def main():
    app = QApplication(sys.argv)
    window = DeliveryApp()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()