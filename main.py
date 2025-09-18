#!/usr/bin/env python3
import socket
import threading
import json
import time
import sys
import os
import configparser
from datetime import datetime
from tkinter import *
from tkinter import ttk, messagebox, scrolledtext
import tkinter.font as tkFont

# Проверка доступности системного трея
try:
    import pystray
    from pystray import MenuItem as item
    from PIL import Image, ImageDraw
    TRAY_AVAILABLE = True
except ImportError:
    TRAY_AVAILABLE = False
    print("Warning: pystray not available, tray functionality disabled")

# Импорт модулей проекта
try:
    from data_processor import DataProcessor
    from receipt_formatter import ReceiptFormatter
except ImportError:
    # Если модули недоступны, создаем заглушки
    class DataProcessor:
        def __init__(self):
            self.json_products = {}
            self.current_transaction_lines = []
            self.transaction_total = 0.0
            self.transaction_active = False
            self.is_return_operation = False
    
    class ReceiptFormatter:
        @staticmethod
        def format_success_receipt(products, total):
            lines = ["=== ЧЕК ==="]
            for product in products.values():
                lines.append(product.get('fPName', ''))
                qty = product.get('fQtty', 0)
                price = product.get('fPrice', 0)
                sum_val = product.get('fSum', 0)
                lines.append(f"{qty} x {price:.2f} = {sum_val:.2f} грн")
            lines.append("")
            lines.append(f"РАЗОМ: {total:.2f} грн")
            lines.append("=== СПЛАЧЕНО ===")
            lines.append("Дякуємо за покупку!")
            return "\n".join(lines)
        
        @staticmethod
        def format_return_receipt(products, total):
            lines = ["=== ПОВЕРНЕННЯ ==="]
            for product in products.values():
                lines.append(f"ПОВЕРНУТО: {product.get('fPName', '')}")
                lines.append(f"Сума: {product.get('fSum', 0):.2f} грн")
            lines.append("")
            lines.append(f"СУМА ПОВЕРНЕННЯ: {total:.2f} грн")
            lines.append("=== ОПЕРАЦІЮ СКАСОВАНО ===")
            return "\n".join(lines)

# Глобальные переменные
products = {}
total = 0.0
clients = []
active = False
prev_products = {}
server_running = False
tcp_log_file = None
udp_socket = None
tcp_socket = None
cli_socket = None
data_processor = DataProcessor()
receipt_formatter = ReceiptFormatter()

# Настройки по умолчанию
DEFAULT_CONFIG = {
    'tcp_status_port': '4000',
    'udp_json_port': '4001', 
    'tcp_client_port': '4002',
    'autostart': 'false',
    'minimize_to_tray': 'false',
    'start_minimized': 'false',
    'log_file': 'tcp_server.log'
}

class POSServerGUI:
    def __init__(self):
        self.root = Tk()
        self.root.title("UniPro POS Server v26")
        self.root.geometry("950x750")
        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)
        
        # Установка иконки
        try:
            self.root.iconbitmap(default='pos.ico')
        except:
            pass
        
        # Переменные для портов и настроек
        self.tcp_status_port = StringVar(value=DEFAULT_CONFIG['tcp_status_port'])
        self.udp_json_port = StringVar(value=DEFAULT_CONFIG['udp_json_port'])
        self.tcp_client_port = StringVar(value=DEFAULT_CONFIG['tcp_client_port'])
        self.autostart = BooleanVar(value=False)
        self.minimize_to_tray = BooleanVar(value=False)
        self.start_minimized = BooleanVar(value=False)
        
        # Загрузка конфигурации
        self.load_config()
        
        # Создание интерфейса
        self.create_widgets()
        
        # Системный трей
        self.tray_icon = None
        if TRAY_AVAILABLE:
            self.setup_tray()
        
        # Проверка на автозапуск и минимизацию
        if self.start_minimized.get() and TRAY_AVAILABLE:
            self.root.after(100, self.hide_window)
        
        # Автозапуск сервера
        if self.autostart.get():
            self.root.after(1000, self.start_server)
    
    def create_widgets(self):
        # Главное меню
        menubar = Menu(self.root)
        self.root.config(menu=menubar)
        
        file_menu = Menu(menubar, tearoff=0)
        menubar.add_cascade(label="Файл", menu=file_menu)
        file_menu.add_command(label="Сохранить конфигурацию", command=self.save_config)
        file_menu.add_command(label="Загрузить конфигурацию", command=self.load_config)
        file_menu.add_separator()
        file_menu.add_command(label="Экспорт config.py", command=self.export_config_py)
        file_menu.add_separator()
        file_menu.add_command(label="Выход", command=self.quit_application)
        
        tools_menu = Menu(menubar, tearoff=0)
        menubar.add_cascade(label="Инструменты", menu=tools_menu)
        tools_menu.add_command(label="Тестировать UDP", command=self.test_udp)
        tools_menu.add_command(label="Тестировать TCP", command=self.test_tcp)
        tools_menu.add_separator()
        tools_menu.add_command(label="Очистить все логи", command=self.clear_all_logs)
        
        # Notebook для вкладок
        notebook = ttk.Notebook(self.root)
        notebook.pack(fill=BOTH, expand=True, padx=10, pady=10)
        
        # Вкладка настроек
        settings_frame = ttk.Frame(notebook)
        notebook.add(settings_frame, text="⚙️ Настройки")
        
        # Настройки портов с валидацией
        ports_frame = ttk.LabelFrame(settings_frame, text="Настройки портов", padding=15)
        ports_frame.pack(fill=X, pady=5, padx=5)
        
        # TCP порт для статусов
        tcp_frame = Frame(ports_frame)
        tcp_frame.grid(row=0, column=0, columnspan=2, sticky=W, pady=5)
        ttk.Label(tcp_frame, text="TCP порт для статусов принтера:").pack(side=LEFT)
        tcp_entry = ttk.Entry(tcp_frame, textvariable=self.tcp_status_port, width=10)
        tcp_entry.pack(side=LEFT, padx=5)
        ttk.Label(tcp_frame, text="(1024-65535)", foreground="gray").pack(side=LEFT)
        
        # UDP порт для JSON
        udp_frame = Frame(ports_frame)
        udp_frame.grid(row=1, column=0, columnspan=2, sticky=W, pady=5)
        ttk.Label(udp_frame, text="UDP порт для JSON данных:").pack(side=LEFT)
        udp_entry = ttk.Entry(udp_frame, textvariable=self.udp_json_port, width=10)
        udp_entry.pack(side=LEFT, padx=5)
        ttk.Label(udp_frame, text="(1024-65535)", foreground="gray").pack(side=LEFT)
        
        # TCP порт для клиентов
        cli_frame = Frame(ports_frame)
        cli_frame.grid(row=2, column=0, columnspan=2, sticky=W, pady=5)
        ttk.Label(cli_frame, text="TCP порт для клиентов:").pack(side=LEFT)
        cli_entry = ttk.Entry(cli_frame, textvariable=self.tcp_client_port, width=10)
        cli_entry.pack(side=LEFT, padx=5)
        ttk.Label(cli_frame, text="(1024-65535)", foreground="gray").pack(side=LEFT)
        
        # Кнопка применения портов
        ttk.Button(ports_frame, text="Применить порты", command=self.apply_ports).grid(row=3, column=0, pady=10, sticky=W)
        
        # Настройки запуска
        startup_frame = ttk.LabelFrame(settings_frame, text="Настройки запуска", padding=15)
        startup_frame.pack(fill=X, pady=5, padx=5)
        
        ttk.Checkbutton(startup_frame, text="Автозапуск сервера при старте программы", 
                       variable=self.autostart).pack(anchor=W, pady=2)
        ttk.Checkbutton(startup_frame, text="Сворачивать в системный трей при закрытии", 
                       variable=self.minimize_to_tray).pack(anchor=W, pady=2)
        ttk.Checkbutton(startup_frame, text="Запускать свернутым в трей", 
                       variable=self.start_minimized).pack(anchor=W, pady=2)
        
        # Добавление в автозагрузку Windows
        autostart_win_frame = ttk.LabelFrame(settings_frame, text="Автозагрузка Windows", padding=15)
        autostart_win_frame.pack(fill=X, pady=5, padx=5)
        
        self.in_startup = BooleanVar(value=self.check_windows_startup())
        ttk.Checkbutton(autostart_win_frame, text="Добавить в автозагрузку Windows", 
                       variable=self.in_startup, command=self.toggle_windows_startup).pack(anchor=W, pady=2)
        ttk.Label(autostart_win_frame, text="(Программа будет запускаться при входе в Windows)", 
                 foreground="gray").pack(anchor=W, padx=20)
        
        # Кнопки управления
        control_frame = ttk.Frame(settings_frame)
        control_frame.pack(fill=X, pady=15, padx=5)
        
        self.start_button = ttk.Button(control_frame, text="▶️ Запустить сервер", 
                                      command=self.start_server, style="Accent.TButton")
        self.start_button.pack(side=LEFT, padx=5)
        
        self.stop_button = ttk.Button(control_frame, text="⏹️ Остановить сервер", 
                                     command=self.stop_server, state=DISABLED)
        self.stop_button.pack(side=LEFT, padx=5)
        
        ttk.Button(control_frame, text="💾 Сохранить настройки", 
                  command=self.save_config).pack(side=LEFT, padx=5)
        
        # Информационная панель
        info_frame = ttk.LabelFrame(settings_frame, text="Статус сервера", padding=15)
        info_frame.pack(fill=X, pady=5, padx=5)
        
        self.server_status = StringVar(value="⭕ Остановлен")
        self.active_transaction = StringVar(value="Нет")
        self.cart_items = StringVar(value="0")
        self.total_amount = StringVar(value="0.00 UAH")
        self.connected_clients = StringVar(value="0")
        
        # Используем grid для лучшего выравнивания
        ttk.Label(info_frame, text="Статус:").grid(row=0, column=0, sticky=W, pady=2)
        status_label = ttk.Label(info_frame, textvariable=self.server_status)
        status_label.grid(row=0, column=1, sticky=W, padx=10, pady=2)
        
        ttk.Label(info_frame, text="Активная транзакция:").grid(row=1, column=0, sticky=W, pady=2)
        ttk.Label(info_frame, textvariable=self.active_transaction).grid(row=1, column=1, sticky=W, padx=10, pady=2)
        
        ttk.Label(info_frame, text="Товаров в корзине:").grid(row=2, column=0, sticky=W, pady=2)
        ttk.Label(info_frame, textvariable=self.cart_items).grid(row=2, column=1, sticky=W, padx=10, pady=2)
        
        ttk.Label(info_frame, text="Сумма:").grid(row=3, column=0, sticky=W, pady=2)
        ttk.Label(info_frame, textvariable=self.total_amount).grid(row=3, column=1, sticky=W, padx=10, pady=2)
        
        ttk.Label(info_frame, text="Подключено клиентов:").grid(row=4, column=0, sticky=W, pady=2)
        ttk.Label(info_frame, textvariable=self.connected_clients).grid(row=4, column=1, sticky=W, padx=10, pady=2)
        
        # Вкладка логов
        log_frame = ttk.Frame(notebook)
        notebook.add(log_frame, text="📝 Логи")
        
        # Панель инструментов для логов
        log_toolbar = ttk.Frame(log_frame)
        log_toolbar.pack(fill=X, padx=5, pady=5)
        
        ttk.Button(log_toolbar, text="Очистить", command=self.clear_logs).pack(side=LEFT, padx=2)
        ttk.Button(log_toolbar, text="Сохранить", command=self.save_logs).pack(side=LEFT, padx=2)
        
        self.autoscroll = BooleanVar(value=True)
        ttk.Checkbutton(log_toolbar, text="Автопрокрутка", variable=self.autoscroll).pack(side=LEFT, padx=10)
        
        # Область логов с улучшенным форматированием
        self.log_text = scrolledtext.ScrolledText(log_frame, height=30, width=100, wrap=WORD)
        self.log_text.pack(fill=BOTH, expand=True, padx=5, pady=5)
        
        # Настройка тегов для цветного вывода
        self.log_text.tag_config("error", foreground="red")
        self.log_text.tag_config("success", foreground="green")
        self.log_text.tag_config("warning", foreground="orange")
        self.log_text.tag_config("info", foreground="blue")
        
        # Вкладка мониторинга
        monitor_frame = ttk.Frame(notebook)
        notebook.add(monitor_frame, text="📊 Мониторинг")
        
        # Текущая корзина
        cart_label_frame = ttk.LabelFrame(monitor_frame, text="Текущая корзина", padding=10)
        cart_label_frame.pack(fill=BOTH, expand=True, padx=5, pady=5)
        
        self.cart_text = scrolledtext.ScrolledText(cart_label_frame, height=15, width=80)
        self.cart_text.pack(fill=BOTH, expand=True)
        
        # Статус бар
        self.status_var = StringVar(value="Сервер остановлен")
        status_bar = ttk.Label(self.root, textvariable=self.status_var, relief=SUNKEN)
        status_bar.pack(side=BOTTOM, fill=X)
        
        # Запуск обновления статуса
        self.update_status()
    
    def send_to_all_clients(self, message):
        """Отправка сообщения всем подключенным клиентам"""
        global clients
        disconnected = []
        for client in clients:
            try:
                client.send(message.encode("utf-8"))
            except:
                disconnected.append(client)
        
        # Удаляем отключенные клиенты
        for client in disconnected:
            try:
                clients.remove(client)
                client.close()
            except:
                pass
    
    def format_product_update(self, action, product_name, product_data=None):
        """Форматирование сообщения об изменении товара"""
        if action == "ADD":
            qty = product_data.get('fQtty', 0) if product_data else 0
            price = product_data.get('fPrice', 0) if product_data else 0
            sum_val = product_data.get('fSum', 0) if product_data else 0
            return f"➕ ДОДАНО: {product_name}\n   {qty} x {price:.2f} = {sum_val:.2f} грн\n"
        
        elif action == "REMOVE":
            return f"➖ ВИДАЛЕНО: {product_name}\n"
        
        elif action == "UPDATE":
            qty = product_data.get('fQtty', 0) if product_data else 0
            price = product_data.get('fPrice', 0) if product_data else 0
            sum_val = product_data.get('fSum', 0) if product_data else 0
            return f"🔄 ОНОВЛЕНО: {product_name}\n   {qty} x {price:.2f} = {sum_val:.2f} грн\n"
        
        return ""
    
    def udp_server(self, port):
        """UDP сервер для приема JSON данных с real-time обновлениями"""
        global products, total, active, prev_products, udp_socket, data_processor
        try:
            udp_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            udp_socket.bind(("0.0.0.0", port))
            self.log(f"UDP сервер запущен на порту {port}", "success")
            
            while server_running:
                try:
                    udp_socket.settimeout(1.0)
                    data, addr = udp_socket.recvfrom(4096)
                    
                    obj = json.loads(data)
                    cmd = obj.get("cmd", {}).get("cmd", "")
                    
                    if cmd == "clear":
                        # Очистка корзины
                        if active:
                            self.send_to_all_clients("❌ === ОПЕРАЦІЮ СКАСОВАНО ===\n\n")
                            self.log("TRANSACTION CANCELLED", "warning")
                        products = {}
                        prev_products = {}
                        total = 0.0
                        active = False
                        data_processor.reset_transaction()
                    else:
                        # Сохраняем старое состояние
                        old_products = dict(prev_products)
                        
                        # Обновляем текущие товары
                        products = {}
                        prev_products = {}
                        
                        for item in obj.get("goods", []):
                            name = item.get("fPName", "")
                            if name:
                                products[name] = item
                                prev_products[name] = item
                        
                        # Если это первый товар - начало транзакции
                        if products and not active:
                            self.send_to_all_clients("🛒 === ПОЧАТОК ОПЕРАЦІЇ ===\n\n")
                            active = True
                            self.log("NEW TRANSACTION STARTED", "success")
                        
                        # REAL-TIME обновления - отправляем изменения клиентам сразу
                        if active:
                            # Проверяем добавленные товары
                            for name, item in products.items():
                                if name not in old_products:
                                    # Новый товар добавлен
                                    msg = self.format_product_update("ADD", name, item)
                                    self.send_to_all_clients(msg)
                                    self.log(f"+ ADDED: {name}", "info")
                                    
                                elif old_products[name].get('fQtty') != item.get('fQtty'):
                                    # Количество товара изменилось
                                    msg = self.format_product_update("UPDATE", name, item)
                                    self.send_to_all_clients(msg)
                                    self.log(f"~ UPDATED: {name}", "info")
                            
                            # Проверяем удаленные товары
                            for name in old_products:
                                if name not in products:
                                    # Товар удален
                                    msg = self.format_product_update("REMOVE", name)
                                    self.send_to_all_clients(msg)
                                    self.log(f"- REMOVED: {name}", "warning")
                            
                            # Обновляем общую сумму
                            old_total = total
                            total = obj.get("sum", {}).get("sum", 0)
                            
                            if total != old_total:
                                self.send_to_all_clients(f"💰 СУМА: {total:.2f} грн\n" + "="*30 + "\n")
                                self.log(f"TOTAL UPDATED: {total:.2f} UAH")
                        
                        if products:
                            self.log(f"CART: {len(products)} items | Total: {total} UAH")
                            
                except socket.timeout:
                    continue
                except Exception as e:
                    if server_running:
                        self.log(f"UDP Error: {e}", "error")
        except Exception as e:
            self.log(f"UDP Server Error: {e}", "error")
    
    def tcp_server(self, port):
        """TCP сервер для приема статусов от принтера"""
        global products, total, clients, active, prev_products, tcp_socket, tcp_log_file
        try:
            tcp_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            tcp_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            tcp_socket.bind(("0.0.0.0", port))
            tcp_socket.listen(5)
            self.log(f"TCP сервер запущен на порту {port}", "success")
            
            # Открытие файла логов
            try:
                tcp_log_file = open("tcp_server.log", "a", buffering=1, encoding="utf-8")
                self.log("TCP log file opened: tcp_server.log")
            except:
                self.log("Warning: Could not open TCP log file", "warning")
            
            while server_running:
                try:
                    tcp_socket.settimeout(1.0)
                    c, a = tcp_socket.accept()
                    self.log(f"TCP connection from {a}")
                    threading.Thread(target=self.handle_tcp_client, args=(c, a), daemon=True).start()
                except socket.timeout:
                    continue
                except Exception as e:
                    if server_running:
                        self.log(f"TCP Accept Error: {e}", "error")
        except Exception as e:
            self.log(f"TCP Server Error: {e}", "error")
    
    def handle_tcp_client(self, client_socket, addr):
        """Обработка TCP клиента с улучшенной проверкой оплаты"""
        global products, total, active, prev_products, tcp_log_file, receipt_formatter
        buf = b""
        try:
            while server_running:
                try:
                    client_socket.settimeout(1.0)
                    d = client_socket.recv(1024)
                    if not d:
                        break
                    buf += d
                    
                    # Детальное логирование
                    if tcp_log_file:
                        tcp_log_file.write("\n" + "="*60 + "\n")
                        tcp_log_file.write(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] From: {addr}\n")
                        tcp_log_file.write(f"RAW bytes ({len(d)}): {d}\n")
                        tcp_log_file.write(f"HEX: {d.hex()}\n")
                        
                        # Пробуем разные декодировки
                        for encoding in ['cp1251', 'utf-8', 'cp1252', 'iso-8859-5']:
                            try:
                                decoded = d.decode(encoding, errors='ignore')
                                tcp_log_file.write(f"{encoding.upper()}: {decoded}\n")
                            except:
                                pass
                        tcp_log_file.flush()
                    
                    # Пробуем декодировать с разными кодировками
                    text = ""
                    for encoding in ['cp1251', 'utf-8', 'cp1252']:
                        try:
                            text = buf.decode(encoding, errors='ignore')
                            break
                        except:
                            continue
                    
                    text_lower = text.lower()
                    
                    # УЛУЧШЕННАЯ ПРОВЕРКА УСПЕШНОЙ ОПЛАТЫ
                    success_patterns = [
                        "дякуємо за покупку",
                        "дякуємо за покупку",  # с другой е
                        "дякуемо за покупку",  # без диакритики
                        "покупку",  # частичное совпадение
                        "сплачено",
                        "оплачено"
                    ]
                    
                    payment_confirmed = False
                    for pattern in success_patterns:
                        if pattern in text_lower:
                            payment_confirmed = True
                            self.log(f"Payment pattern matched: '{pattern}'", "info")
                            break
                    
                    # Проверка по HEX паттернам
                    hex_data = buf.hex().lower()
                    hex_patterns = [
                        "c4ffea",  # "Дяк" в CP1251
                        "d0b4d18f",  # "Дя" в UTF-8
                        "efeeea",  # "пок" в CP1251
                    ]
                    
                    for hex_pattern in hex_patterns:
                        if hex_pattern in hex_data:
                            payment_confirmed = True
                            self.log(f"Payment HEX pattern matched: {hex_pattern}", "info")
                            break
                    
                    # Проверка возврата
                    if "повернення" in text_lower or "возврат" in text_lower:
                        self.log("RETURN OPERATION DETECTED", "warning")
                        if products:
                            msg = receipt_formatter.format_return_receipt(products, total)
                            self.send_to_all_clients(msg)
                            self.log(f"RETURN COMPLETE | Total: {total} UAH", "warning")
                        else:
                            msg = "=== ПОВЕРНЕННЯ ===\nПовернення виконано\n=== ОПЕРАЦІЮ СКАСОВАНО ===\n"
                            self.send_to_all_clients(msg)
                            self.log("RETURN WITHOUT PRODUCTS", "warning")
                        
                        # Очистка данных
                        products = {}
                        prev_products = {}
                        total = 0.0
                        active = False
                        data_processor.reset_transaction()
                        break
                    
                    # Проверка успешной оплаты
                    elif payment_confirmed and products:
                        self.log("PAYMENT CONFIRMED - Transaction complete!", "success")
                        self.log(f"Matched text: '{text[:100]}'", "info")
                        
                        # Отправляем финальный чек
                        msg = "\n" + "="*40 + "\n"
                        msg += receipt_formatter.format_success_receipt(products, total)
                        msg += "\n" + "="*40 + "\n"
                        
                        self.send_to_all_clients(msg)
                        self.log(f"TRANSACTION COMPLETE | Total: {total} UAH", "success")
                        
                        # Очистка данных
                        products = {}
                        prev_products = {}
                        total = 0.0
                        active = False
                        data_processor.reset_transaction()
                        break
                    
                    # Логируем, если не распознали
                    elif len(buf) > 0:
                        self.log(f"TCP data not recognized: {text[:50]}", "warning")
                        
                except socket.timeout:
                    continue
                except Exception as e:
                    if server_running:
                        self.log(f"TCP Client Error: {e}", "error")
                    break
                    
        except Exception as e:
            self.log(f"TCP Handle Error: {e}", "error")
        finally:
            client_socket.close()
            self.log(f"TCP connection closed: {addr}")
    
    def client_server(self, port):
        """TCP сервер для клиентских подключений"""
        global clients, cli_socket
        try:
            cli_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            cli_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            cli_socket.bind(("0.0.0.0", port))
            cli_socket.listen(10)
            self.log(f"Client сервер запущен на порту {port}", "success")
            
            while server_running:
                try:
                    cli_socket.settimeout(1.0)
                    c, a = cli_socket.accept()
                    self.log(f"CLIENT CONNECTED: {a}", "info")
                    clients.append(c)
                    
                    # Отправка приветственного сообщения
                    try:
                        welcome_msg = "🔌 === UniPro POS Server v26 ===\n"
                        welcome_msg += "📡 Real-time updates enabled\n"
                        welcome_msg += "⏳ Waiting for transaction...\n"
                        welcome_msg += "="*40 + "\n"
                        c.send(welcome_msg.encode("utf-8"))
                    except:
                        pass
                        
                except socket.timeout:
                    continue
                except Exception as e:
                    if server_running:
                        self.log(f"Client Server Error: {e}", "error")
        except Exception as e:
            self.log(f"Client Server Error: {e}", "error")
    
    def apply_ports(self):
        """Применение измененных портов и обновление config.py"""
        try:
            # Валидация портов
            tcp_status = int(self.tcp_status_port.get())
            udp_json = int(self.udp_json_port.get())
            tcp_client = int(self.tcp_client_port.get())
            
            if not all(1024 <= p <= 65535 for p in [tcp_status, udp_json, tcp_client]):
                raise ValueError("Порты должны быть в диапазоне 1024-65535")
            
            # Проверка на дубликаты
            if len(set([tcp_status, udp_json, tcp_client])) != 3:
                raise ValueError("Порты должны быть уникальными")
            
            # Обновление config.py
            self.update_config_py(tcp_status, udp_json, tcp_client)
            
            # Сохранение в конфигурацию
            self.save_config()
            
            messagebox.showinfo("Успех", "Порты успешно применены!\nПерезапустите сервер для применения изменений.")
            
            # Если сервер работает, предложить перезапуск
            if server_running:
                if messagebox.askyesno("Перезапуск", "Сервер работает. Перезапустить сейчас?"):
                    self.stop_server()
                    self.root.after(500, self.start_server)
                    
        except ValueError as e:
            messagebox.showerror("Ошибка", str(e))
        except Exception as e:
            messagebox.showerror("Ошибка", f"Не удалось применить порты: {e}")
    
    def update_config_py(self, tcp_status, udp_json, tcp_client):
        """Обновление файла config.py с новыми портами"""
        config_content = f'''# Сетевые настройки
TCP_STATUS_PORT = {tcp_status}    # TCP для статусов от принтера
UDP_JSON_PORT = {udp_json}      # UDP для JSON данных от принтера
TCP_CLIENT_PORT = {tcp_client}    # TCP для отправки клиентам

# Кодировки
ENCODINGS = ['utf-8', 'cp1251', 'ascii', 'latin1']

# Индикаторы операций
SUCCESS_INDICATORS = ["Дякуємо за покупку", "дякуємо за покупку", "покупку", "сплачено"]
RETURN_INDICATORS = ["Повернення", "повернення", "Возврат", "возврат"]
DELETE_INDICATORS = ["Видалено товар:", "видалено товар:"]

# HEX паттерны для надежного определения
SUCCESS_HEX_PATTERNS = ["c4ffea", "d0b4d18f", "efeeea"]
'''
        
        try:
            with open('config.py', 'w', encoding='utf-8') as f:
                f.write(config_content)
            self.log("config.py обновлен с новыми портами", "success")
        except Exception as e:
            self.log(f"Ошибка обновления config.py: {e}", "error")
    
    def export_config_py(self):
        """Экспорт текущих настроек в config.py"""
        try:
            tcp_status = int(self.tcp_status_port.get())
            udp_json = int(self.udp_json_port.get())
            tcp_client = int(self.tcp_client_port.get())
            
            self.update_config_py(tcp_status, udp_json, tcp_client)
            messagebox.showinfo("Успех", "config.py успешно экспортирован!")
        except Exception as e:
            messagebox.showerror("Ошибка", f"Не удалось экспортировать config.py: {e}")
    
    def test_udp(self):
        """Отправка тестового UDP сообщения"""
        test_data = {
            "cmd": {"cmd": ""},
            "goods": [
                {
                    "fPName": "Тестовый товар 1",
                    "fPrice": 15.50,
                    "fQtty": 2,
                    "fSum": 31.00
                },
                {
                    "fPName": "Тестовый товар 2",
                    "fPrice": 25.00,
                    "fQtty": 1,
                    "fSum": 25.00
                }
            ],
            "sum": {"sum": 56.00}
        }
        
        try:
            test_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            test_socket.sendto(json.dumps(test_data).encode(), ('localhost', int(self.udp_json_port.get())))
            test_socket.close()
            self.log("Тестовое UDP сообщение отправлено", "info")
            messagebox.showinfo("Тест UDP", "Тестовое сообщение отправлено успешно!")
        except Exception as e:
            self.log(f"Ошибка отправки тестового сообщения: {e}", "error")
            messagebox.showerror("Ошибка", f"Не удалось отправить тестовое сообщение: {e}")
    
    def test_tcp(self):
        """Тестирование TCP соединения"""
        try:
            test_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            test_socket.settimeout(2)
            test_socket.connect(('localhost', int(self.tcp_status_port.get())))
            test_socket.send("Дякуємо за покупку".encode('cp1251'))
            test_socket.close()
            self.log("Тестовое TCP сообщение отправлено", "info")
            messagebox.showinfo("Тест TCP", "TCP тест выполнен успешно!")
        except Exception as e:
            self.log(f"Ошибка TCP теста: {e}", "error")
            messagebox.showerror("Ошибка", f"TCP тест не удался: {e}")
    
    # ... остальные методы остаются без изменений ...
    
    def check_windows_startup(self):
        """Проверка наличия в автозагрузке Windows"""
        try:
            import winreg
            key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, 
                               r"Software\Microsoft\Windows\CurrentVersion\Run", 
                               0, winreg.KEY_READ)
            try:
                winreg.QueryValueEx(key, "UniProPOSServer")
                winreg.CloseKey(key)
                return True
            except:
                winreg.CloseKey(key)
                return False
        except:
            return False
    
    def toggle_windows_startup(self):
        """Добавление/удаление из автозагрузки Windows"""
        try:
            import winreg
            key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, 
                               r"Software\Microsoft\Windows\CurrentVersion\Run", 
                               0, winreg.KEY_SET_VALUE)
            
            if self.in_startup.get():
                exe_path = os.path.abspath(sys.argv[0])
                if exe_path.endswith('.py'):
                    exe_path = f'"{sys.executable}" "{exe_path}"'
                else:
                    exe_path = f'"{exe_path}"'
                winreg.SetValueEx(key, "UniProPOSServer", 0, winreg.REG_SZ, exe_path)
                messagebox.showinfo("Успех", "Программа добавлена в автозагрузку Windows")
            else:
                try:
                    winreg.DeleteValue(key, "UniProPOSServer")
                    messagebox.showinfo("Успех", "Программа удалена из автозагрузки Windows")
                except:
                    pass
            
            winreg.CloseKey(key)
        except Exception as e:
            messagebox.showerror("Ошибка", f"Не удалось изменить автозагрузку: {e}")
            self.in_startup.set(not self.in_startup.get())
    
    def update_status(self):
        """Обновление статуса в реальном времени"""
        global server_running, active, products, total, clients
        
        self.server_status.set("🟢 Работает" if server_running else "⭕ Остановлен")
        self.active_transaction.set("Да" if active else "Нет")
        self.cart_items.set(str(len(products)))
        self.total_amount.set(f"{total:.2f} UAH")
        self.connected_clients.set(str(len(clients)))
        
        # Обновление корзины в мониторинге
        if products:
            cart_info = "=== ТЕКУЩАЯ КОРЗИНА ===\n"
            for name, item in products.items():
                qty = item.get('fQtty', 0)
                price = item.get('fPrice', 0)
                sum_val = item.get('fSum', 0)
                cart_info += f"\n{name}\n  {qty} x {price:.2f} = {sum_val:.2f} грн\n"
            cart_info += f"\n{'='*30}\nИТОГО: {total:.2f} грн"
            
            self.cart_text.delete(1.0, END)
            self.cart_text.insert(END, cart_info)
        else:
            self.cart_text.delete(1.0, END)
            self.cart_text.insert(END, "Корзина пуста")
        
        # Обновление статус бара
        if server_running:
            self.status_var.set(f"Сервер работает | Порты: TCP {self.tcp_status_port.get()}, "
                               f"UDP {self.udp_json_port.get()}, Client {self.tcp_client_port.get()}")
        else:
            self.status_var.set("Сервер остановлен")
        
        # Повторный вызов через 1 секунду
        self.root.after(1000, self.update_status)
    
    def start_server(self):
        global server_running
        if server_running:
            self.log("Сервер уже работает", "warning")
            return
            
        try:
            tcp_status = int(self.tcp_status_port.get())
            udp_json = int(self.udp_json_port.get())
            tcp_client = int(self.tcp_client_port.get())
            
            if not all(1024 <= p <= 65535 for p in [tcp_status, udp_json, tcp_client]):
                raise ValueError("Порты должны быть в диапазоне 1024-65535")
            
            threading.Thread(target=self.udp_server, args=(udp_json,), daemon=True).start()
            threading.Thread(target=self.tcp_server, args=(tcp_status,), daemon=True).start()
            threading.Thread(target=self.client_server, args=(tcp_client,), daemon=True).start()
            
            server_running = True
            
            self.log(f"Сервер запущен на портах: TCP {tcp_status}, UDP {udp_json}, TCP Client {tcp_client}", "success")
            
            self.start_button.config(state=DISABLED)
            self.stop_button.config(state=NORMAL)
            
        except Exception as e:
            messagebox.showerror("Ошибка", f"Не удалось запустить сервер: {e}")
            self.log(f"Ошибка запуска сервера: {e}", "error")
    
    def stop_server(self):
        global server_running, udp_socket, tcp_socket, cli_socket, tcp_log_file, clients
        server_running = False
        
        for client in clients:
            try:
                client.close()
            except:
                pass
        clients = []
        
        try:
            if udp_socket:
                udp_socket.close()
                udp_socket = None
            if tcp_socket:
                tcp_socket.close()
                tcp_socket = None
            if cli_socket:
                cli_socket.close()
                cli_socket = None
            if tcp_log_file:
                tcp_log_file.close()
                tcp_log_file = None
        except:
            pass
        
        self.log("Сервер остановлен", "warning")
        
        self.start_button.config(state=NORMAL)
        self.stop_button.config(state=DISABLED)
    
    def log(self, message, tag=None):
        """Улучшенное логирование с тегами"""
        timestamp = datetime.now().strftime("[%H:%M:%S]")
        log_message = f"{timestamp} {message}\n"
        
        try:
            if hasattr(self, 'log_text') and self.log_text.winfo_exists():
                self.log_text.insert(END, log_message, tag)
                if self.autoscroll.get():
                    self.log_text.see(END)
        except:
            pass
        
        try:
            print(log_message.strip())
        except:
            pass
        
        try:
            with open("pos_server.log", "a", encoding="utf-8") as f:
                f.write(log_message)
        except:
            pass
    
    def clear_logs(self):
        self.log_text.delete(1.0, END)
        self.log("Логи очищены", "info")
    
    def clear_all_logs(self):
        if messagebox.askyesno("Подтверждение", "Очистить все файлы логов?"):
            self.clear_logs()
            try:
                for log_file in ['pos_server.log', 'tcp_server.log', 'tcp_4000.log']:
                    if os.path.exists(log_file):
                        os.remove(log_file)
                self.log("Все файлы логов очищены", "success")
            except Exception as e:
                self.log(f"Ошибка очистки файлов логов: {e}", "error")
    
    def save_logs(self):
        from tkinter.filedialog import asksaveasfilename
        filename = asksaveasfilename(
            defaultextension=".log",
            filetypes=[("Log files", "*.log"), ("Text files", "*.txt"), ("All files", "*.*")]
        )
        if filename:
            try:
                with open(filename, 'w', encoding='utf-8') as f:
                    f.write(self.log_text.get(1.0, END))
                messagebox.showinfo("Успех", "Логи сохранены")
            except Exception as e:
                messagebox.showerror("Ошибка", f"Не удалось сохранить логи: {e}")
    
    def save_config(self):
        config = configparser.ConfigParser()
        config['SETTINGS'] = {
            'tcp_status_port': self.tcp_status_port.get(),
            'udp_json_port': self.udp_json_port.get(),
            'tcp_client_port': self.tcp_client_port.get(),
            'autostart': str(self.autostart.get()),
            'minimize_to_tray': str(self.minimize_to_tray.get()),
            'start_minimized': str(self.start_minimized.get())
        }
        
        try:
            with open('pos_server_config.ini', 'w') as f:
                config.write(f)
            self.log("Конфигурация сохранена", "success")
        except Exception as e:
            messagebox.showerror("Ошибка", f"Не удалось сохранить конфигурацию: {e}")
    
    def load_config(self):
        config = configparser.ConfigParser()
        try:
            config.read('pos_server_config.ini')
            if 'SETTINGS' in config:
                settings = config['SETTINGS']
                self.tcp_status_port.set(settings.get('tcp_status_port', DEFAULT_CONFIG['tcp_status_port']))
                self.udp_json_port.set(settings.get('udp_json_port', DEFAULT_CONFIG['udp_json_port']))
                self.tcp_client_port.set(settings.get('tcp_client_port', DEFAULT_CONFIG['tcp_client_port']))
                self.autostart.set(settings.getboolean('autostart', False))
                self.minimize_to_tray.set(settings.getboolean('minimize_to_tray', False))
                self.start_minimized.set(settings.getboolean('start_minimized', False))
                self.log("Конфигурация загружена", "info")
        except Exception as e:
            self.log(f"Ошибка загрузки конфигурации: {e}", "warning")
    
    def setup_tray(self):
        if not TRAY_AVAILABLE:
            return
            
        def create_image():
            width = 64
            height = 64
            image = Image.new('RGB', (width, height), color='#2c3e50')
            dc = ImageDraw.Draw(image)
            dc.rectangle([10, 10, width-10, height-10], fill='#3498db')
            dc.text((20, 20), "POS", fill='white')
            return image
        
        menu = pystray.Menu(
            item('Показать', self.show_window, default=True),
            item('Запустить сервер', lambda: self.root.after(0, self.start_server)),
            item('Остановить сервер', lambda: self.root.after(0, self.stop_server)),
            pystray.Menu.SEPARATOR,
            item('Выход', self.quit_from_tray)
        )
        
        self.tray_icon = pystray.Icon("pos_server", create_image(), "UniPro POS Server", menu)
    
    def on_closing(self):
        if self.minimize_to_tray.get() and TRAY_AVAILABLE:
            self.hide_window()
        else:
            if server_running:
                if messagebox.askyesno("Подтверждение", "Сервер работает. Остановить и выйти?"):
                    self.quit_application()
            else:
                self.quit_application()
    
    def hide_window(self):
        self.root.withdraw()
        if self.tray_icon and not self.tray_icon.visible:
            threading.Thread(target=self.tray_icon.run, daemon=True).start()
        self.log("Программа свернута в трей", "info")
    
    def show_window(self, icon=None, item=None):
        self.root.deiconify()
        self.root.lift()
        self.root.focus_force()
        if self.tray_icon:
            self.tray_icon.stop()
    
    def quit_from_tray(self, icon, item):
        icon.stop()
        self.root.after(0, self.quit_application)
    
    def quit_application(self):
        self.stop_server()
        if self.tray_icon:
            self.tray_icon.stop()
        self.save_config()
        self.root.quit()
        self.root.destroy()
        sys.exit(0)
    
    def run(self):
        self.root.mainloop()

if __name__ == "__main__":
    print("UniPro POS Server v26 with Real-Time Updates")
    print("="*50)
    app = POSServerGUI()
    app.run()
