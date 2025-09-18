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

# Перевірка доступності системного трею
try:
    import pystray
    from pystray import MenuItem as item
    from PIL import Image, ImageDraw
    TRAY_AVAILABLE = True
except ImportError:
    TRAY_AVAILABLE = False
    print("Увага: pystray недоступний, функції трею вимкнено")

# Імпорт модулів проекту
try:
    from data_processor import DataProcessor
    from receipt_formatter import ReceiptFormatter
except ImportError:
    # Якщо модулі недоступні, створюємо заглушки
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

# Глобальні змінні
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
last_total_sent = 0.0  # Для відстеження останньої відправленої суми

# Налаштування за замовчуванням
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
        self.root.title("UniPro POS Server v28")
        self.root.geometry("950x750")
        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)
        
        # Встановлення іконки
        try:
            self.root.iconbitmap(default='pos.ico')
        except:
            pass
        
        # Змінні для портів і налаштувань
        self.tcp_status_port = StringVar(value=DEFAULT_CONFIG['tcp_status_port'])
        self.udp_json_port = StringVar(value=DEFAULT_CONFIG['udp_json_port'])
        self.tcp_client_port = StringVar(value=DEFAULT_CONFIG['tcp_client_port'])
        self.autostart = BooleanVar(value=False)
        self.minimize_to_tray = BooleanVar(value=False)
        self.start_minimized = BooleanVar(value=False)
        
        # Завантаження конфігурації
        self.load_config()
        
        # Створення інтерфейсу
        self.create_widgets()
        
        # Системний трей
        self.tray_icon = None
        if TRAY_AVAILABLE:
            self.setup_tray()
        
        # Перевірка на автозапуск і мінімізацію
        if self.start_minimized.get() and TRAY_AVAILABLE:
            self.root.after(100, self.hide_window)
        
        # Автозапуск сервера
        if self.autostart.get():
            self.root.after(1000, self.start_server)
    
    def create_widgets(self):
        # Головне меню
        menubar = Menu(self.root)
        self.root.config(menu=menubar)
        
        file_menu = Menu(menubar, tearoff=0)
        menubar.add_cascade(label="Файл", menu=file_menu)
        file_menu.add_command(label="Зберегти конфігурацію", command=self.save_config)
        file_menu.add_command(label="Завантажити конфігурацію", command=self.load_config)
        file_menu.add_separator()
        file_menu.add_command(label="Експорт config.py", command=self.export_config_py)
        file_menu.add_separator()
        file_menu.add_command(label="Вихід", command=self.quit_application)
        
        tools_menu = Menu(menubar, tearoff=0)
        menubar.add_cascade(label="Інструменти", menu=tools_menu)
        tools_menu.add_command(label="Тестувати UDP", command=self.test_udp)
        tools_menu.add_command(label="Тестувати TCP", command=self.test_tcp)
        tools_menu.add_separator()
        tools_menu.add_command(label="Очистити всі логи", command=self.clear_all_logs)
        
        # Notebook для вкладок
        notebook = ttk.Notebook(self.root)
        notebook.pack(fill=BOTH, expand=True, padx=10, pady=10)
        
        # Вкладка налаштувань
        settings_frame = ttk.Frame(notebook)
        notebook.add(settings_frame, text="⚙️ Налаштування")
        
        # Налаштування портів з валідацією
        ports_frame = ttk.LabelFrame(settings_frame, text="Налаштування портів", padding=15)
        ports_frame.pack(fill=X, pady=5, padx=5)
        
        # TCP порт для статусів
        tcp_frame = Frame(ports_frame)
        tcp_frame.grid(row=0, column=0, columnspan=2, sticky=W, pady=5)
        ttk.Label(tcp_frame, text="TCP порт для статусів принтера:").pack(side=LEFT)
        tcp_entry = ttk.Entry(tcp_frame, textvariable=self.tcp_status_port, width=10)
        tcp_entry.pack(side=LEFT, padx=5)
        ttk.Label(tcp_frame, text="(1024-65535)", foreground="gray").pack(side=LEFT)
        
        # UDP порт для JSON
        udp_frame = Frame(ports_frame)
        udp_frame.grid(row=1, column=0, columnspan=2, sticky=W, pady=5)
        ttk.Label(udp_frame, text="UDP порт для JSON даних:").pack(side=LEFT)
        udp_entry = ttk.Entry(udp_frame, textvariable=self.udp_json_port, width=10)
        udp_entry.pack(side=LEFT, padx=5)
        ttk.Label(udp_frame, text="(1024-65535)", foreground="gray").pack(side=LEFT)
        
        # TCP порт для клієнтів
        cli_frame = Frame(ports_frame)
        cli_frame.grid(row=2, column=0, columnspan=2, sticky=W, pady=5)
        ttk.Label(cli_frame, text="TCP порт для клієнтів:").pack(side=LEFT)
        cli_entry = ttk.Entry(cli_frame, textvariable=self.tcp_client_port, width=10)
        cli_entry.pack(side=LEFT, padx=5)
        ttk.Label(cli_frame, text="(1024-65535)", foreground="gray").pack(side=LEFT)
        
        # Кнопка застосування портів
        ttk.Button(ports_frame, text="Застосувати порти", command=self.apply_ports).grid(row=3, column=0, pady=10, sticky=W)
        
        # Налаштування запуску
        startup_frame = ttk.LabelFrame(settings_frame, text="Налаштування запуску", padding=15)
        startup_frame.pack(fill=X, pady=5, padx=5)
        
        ttk.Checkbutton(startup_frame, text="Автозапуск сервера при старті програми", 
                       variable=self.autostart).pack(anchor=W, pady=2)
        ttk.Checkbutton(startup_frame, text="Згортати в системний трей при закритті", 
                       variable=self.minimize_to_tray).pack(anchor=W, pady=2)
        ttk.Checkbutton(startup_frame, text="Запускати згорнутим в трей", 
                       variable=self.start_minimized).pack(anchor=W, pady=2)
        
        # Додавання в автозавантаження Windows
        autostart_win_frame = ttk.LabelFrame(settings_frame, text="Автозавантаження Windows", padding=15)
        autostart_win_frame.pack(fill=X, pady=5, padx=5)
        
        self.in_startup = BooleanVar(value=self.check_windows_startup())
        ttk.Checkbutton(autostart_win_frame, text="Додати в автозавантаження Windows", 
                       variable=self.in_startup, command=self.toggle_windows_startup).pack(anchor=W, pady=2)
        ttk.Label(autostart_win_frame, text="(Програма буде запускатись при вході в Windows)", 
                 foreground="gray").pack(anchor=W, padx=20)
        
        # Кнопки управління
        control_frame = ttk.Frame(settings_frame)
        control_frame.pack(fill=X, pady=15, padx=5)
        
        self.start_button = ttk.Button(control_frame, text="▶️ Запустити сервер", 
                                      command=self.start_server, style="Accent.TButton")
        self.start_button.pack(side=LEFT, padx=5)
        
        self.stop_button = ttk.Button(control_frame, text="⏹️ Зупинити сервер", 
                                     command=self.stop_server, state=DISABLED)
        self.stop_button.pack(side=LEFT, padx=5)
        
        ttk.Button(control_frame, text="💾 Зберегти налаштування", 
                  command=self.save_config).pack(side=LEFT, padx=5)
        
        # Інформаційна панель
        info_frame = ttk.LabelFrame(settings_frame, text="Статус сервера", padding=15)
        info_frame.pack(fill=X, pady=5, padx=5)
        
        self.server_status = StringVar(value="⭕ Зупинено")
        self.active_transaction = StringVar(value="Ні")
        self.cart_items = StringVar(value="0")
        self.total_amount = StringVar(value="0.00 грн")
        self.connected_clients = StringVar(value="0")
        
        # Використовуємо grid для кращого вирівнювання
        ttk.Label(info_frame, text="Статус:").grid(row=0, column=0, sticky=W, pady=2)
        status_label = ttk.Label(info_frame, textvariable=self.server_status)
        status_label.grid(row=0, column=1, sticky=W, padx=10, pady=2)
        
        ttk.Label(info_frame, text="Активна транзакція:").grid(row=1, column=0, sticky=W, pady=2)
        ttk.Label(info_frame, textvariable=self.active_transaction).grid(row=1, column=1, sticky=W, padx=10, pady=2)
        
        ttk.Label(info_frame, text="Товарів у кошику:").grid(row=2, column=0, sticky=W, pady=2)
        ttk.Label(info_frame, textvariable=self.cart_items).grid(row=2, column=1, sticky=W, padx=10, pady=2)
        
        ttk.Label(info_frame, text="Сума:").grid(row=3, column=0, sticky=W, pady=2)
        ttk.Label(info_frame, textvariable=self.total_amount).grid(row=3, column=1, sticky=W, padx=10, pady=2)
        
        ttk.Label(info_frame, text="Підключено клієнтів:").grid(row=4, column=0, sticky=W, pady=2)
        ttk.Label(info_frame, textvariable=self.connected_clients).grid(row=4, column=1, sticky=W, padx=10, pady=2)
        
        # Вкладка логів
        log_frame = ttk.Frame(notebook)
        notebook.add(log_frame, text="📝 Логи")
        
        # Панель інструментів для логів
        log_toolbar = ttk.Frame(log_frame)
        log_toolbar.pack(fill=X, padx=5, pady=5)
        
        ttk.Button(log_toolbar, text="Очистити", command=self.clear_logs).pack(side=LEFT, padx=2)
        ttk.Button(log_toolbar, text="Зберегти", command=self.save_logs).pack(side=LEFT, padx=2)
        
        self.autoscroll = BooleanVar(value=True)
        ttk.Checkbutton(log_toolbar, text="Автопрокрутка", variable=self.autoscroll).pack(side=LEFT, padx=10)
        
        # Область логів з покращеним форматуванням
        self.log_text = scrolledtext.ScrolledText(log_frame, height=30, width=100, wrap=WORD)
        self.log_text.pack(fill=BOTH, expand=True, padx=5, pady=5)
        
        # Налаштування тегів для кольорового виводу
        self.log_text.tag_config("error", foreground="red")
        self.log_text.tag_config("success", foreground="green")
        self.log_text.tag_config("warning", foreground="orange")
        self.log_text.tag_config("info", foreground="blue")
        
        # Вкладка моніторингу
        monitor_frame = ttk.Frame(notebook)
        notebook.add(monitor_frame, text="📊 Моніторинг")
        
        # Поточний кошик
        cart_label_frame = ttk.LabelFrame(monitor_frame, text="Поточний кошик", padding=10)
        cart_label_frame.pack(fill=BOTH, expand=True, padx=5, pady=5)
        
        self.cart_text = scrolledtext.ScrolledText(cart_label_frame, height=15, width=80)
        self.cart_text.pack(fill=BOTH, expand=True)
        
        # Статус бар
        self.status_var = StringVar(value="Сервер зупинено")
        status_bar = ttk.Label(self.root, textvariable=self.status_var, relief=SUNKEN)
        status_bar.pack(side=BOTTOM, fill=X)
        
        # Запуск оновлення статусу
        self.update_status()
    
    def send_to_all_clients(self, message):
        """Відправка повідомлення всім підключеним клієнтам"""
        global clients
        disconnected = []
        for client in clients:
            try:
                client.send(message.encode("utf-8"))
            except:
                disconnected.append(client)
        
        # Видаляємо відключені клієнти
        for client in disconnected:
            try:
                clients.remove(client)
                client.close()
            except:
                pass
    
    def format_product_update(self, action, product_name, product_data=None, old_data=None):
        """Форматування повідомлення про зміну товару - БЕЗ ANSI КОДІВ"""
        if action == "ADD":
            qty = product_data.get('fQtty', 0) if product_data else 0
            price = product_data.get('fPrice', 0) if product_data else 0
            sum_val = product_data.get('fSum', 0) if product_data else 0
            # Просто плюс без зайвого
            return f"+ {product_name}  {qty}x{price:.2f} = {sum_val:.2f} грн\n"
        
        elif action == "REMOVE":
            qty = old_data.get('fQtty', 0) if old_data else 0
            price = old_data.get('fPrice', 0) if old_data else 0  
            sum_val = old_data.get('fSum', 0) if old_data else 0
            # Просто мінус
            return f"- {product_name}  {qty}x{price:.2f} = {sum_val:.2f} грн\n"
        
        elif action == "UPDATE":
            old_qty = old_data.get('fQtty', 0) if old_data else 0
            new_qty = product_data.get('fQtty', 0) if product_data else 0
            price = product_data.get('fPrice', 0) if product_data else 0
            sum_val = product_data.get('fSum', 0) if product_data else 0
            
            if new_qty > old_qty:
                # Збільшення кількості
                diff = new_qty - old_qty
                return f"+ {product_name}  +{diff} (всього: {new_qty}x{price:.2f} = {sum_val:.2f} грн)\n"
            else:
                # Зменшення кількості
                diff = old_qty - new_qty
                return f"- {product_name}  -{diff} (всього: {new_qty}x{price:.2f} = {sum_val:.2f} грн)\n"
        
        return ""
    
    def udp_server(self, port):
        """UDP сервер для прийому JSON даних з правильним підрахунком кількості"""
        global products, total, active, prev_products, udp_socket, data_processor, last_total_sent
        
        try:
            udp_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            udp_socket.bind(("0.0.0.0", port))
            self.log(f"UDP сервер запущено на порту {port}", "success")
            
            while server_running:
                try:
                    udp_socket.settimeout(1.0)
                    data, addr = udp_socket.recvfrom(4096)
                    
                    obj = json.loads(data)
                    cmd = obj.get("cmd", {}).get("cmd", "")
                    
                    if cmd == "clear":
                        # Простіша логіка - просто перевіряємо флаг active
                        if active:
                            # Відправляємо скасування тільки якщо транзакція активна
                            self.send_to_all_clients("❌ === ОПЕРАЦІЮ СКАСОВАНО ===\n\n")
                            self.log("ТРАНЗАКЦІЮ СКАСОВАНО", "warning")
                        else:
                            self.log("Clear received - no active transaction", "info")
                        
                        # Очищаємо дані в будь-якому випадку
                        products = {}
                        prev_products = {}
                        total = 0.0
                        active = False
                        last_total_sent = 0.0
                        data_processor.reset_transaction()
                    else:
                        # Зберігаємо старий стан
                        old_products = dict(prev_products)
                        
                        # Оновлюємо поточні товари
                        products = {}
                        prev_products = {}
                        
                        for item in obj.get("goods", []):
                            name = item.get("fPName", "")
                            if name:
                                products[name] = item
                                prev_products[name] = item
                        
                        # Якщо це перший товар - початок транзакції
                        if products and not active:
                            self.send_to_all_clients("🛒 === ПОЧАТОК ОПЕРАЦІЇ ===\n\n")
                            active = True
                            last_total_sent = 0.0
                            self.log("НОВА ТРАНЗАКЦІЯ РОЗПОЧАТА", "success")
                        
                        # REAL-TIME оновлення з правильною обробкою кількості
                        if active:
                            changes_made = False
                            
                            # Перевіряємо зміни в товарах
                            for name, item in products.items():
                                if name not in old_products:
                                    # Новий товар додано
                                    msg = self.format_product_update("ADD", name, item)
                                    self.send_to_all_clients(msg)
                                    self.log(f"+ ДОДАНО: {name}", "info")
                                    changes_made = True
                                    
                                elif (old_products[name].get('fQtty') != item.get('fQtty') or
                                      old_products[name].get('fSum') != item.get('fSum')):
                                    # Кількість або сума змінилась
                                    msg = self.format_product_update("UPDATE", name, item, old_products[name])
                                    self.send_to_all_clients(msg)
                                    self.log(f"~ ОНОВЛЕНО: {name} (кількість: {item.get('fQtty')})", "info")
                                    changes_made = True
                            
                            # Перевіряємо видалені товари
                            for name in old_products:
                                if name not in products:
                                    # Товар видалено
                                    msg = self.format_product_update("REMOVE", name, None, old_products[name])
                                    self.send_to_all_clients(msg)
                                    self.log(f"- ВИДАЛЕНО: {name}", "warning")
                                    changes_made = True
                            
                            # Оновлюємо загальну суму ТІЛЬКИ якщо були зміни і сума дійсно змінилась
                            total = obj.get("sum", {}).get("sum", 0)
                            
                            # Відправляємо суму тільки якщо:
                            # 1. Були зміни в товарах
                            # 2. Сума дійсно змінилась більш ніж на 0.01
                            if changes_made and abs(total - last_total_sent) > 0.01:
                                self.send_to_all_clients(f"💰 СУМА: {total:.2f} грн\n" + "="*30 + "\n")
                                last_total_sent = total
                                self.log(f"СУМА ОНОВЛЕНА: {total:.2f} грн")
                        
                        if products:
                            # Підраховуємо унікальні товари (не кількість одиниць)
                            unique_items = len(products)
                            total_units = sum(item.get('fQtty', 0) for item in products.values())
                            self.log(f"КОШИК: {unique_items} товарів ({total_units} одиниць) | Сума: {total} грн")
                            
                except socket.timeout:
                    continue
                except Exception as e:
                    if server_running:
                        self.log(f"UDP помилка: {e}", "error")
        except Exception as e:
            self.log(f"UDP сервер помилка: {e}", "error")
    
    def tcp_server(self, port):
        """TCP сервер для прийому статусів від принтера"""
        global products, total, clients, active, prev_products, tcp_socket, tcp_log_file, last_total_sent
        try:
            tcp_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            tcp_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            tcp_socket.bind(("0.0.0.0", port))
            tcp_socket.listen(5)
            self.log(f"TCP сервер запущено на порту {port}", "success")
            
            # Відкриття файлу логів
            try:
                tcp_log_file = open("tcp_server.log", "a", buffering=1, encoding="utf-8")
                self.log("TCP файл логів відкрито: tcp_server.log")
            except:
                self.log("Увага: не вдалось відкрити TCP файл логів", "warning")
            
            while server_running:
                try:
                    tcp_socket.settimeout(1.0)
                    c, a = tcp_socket.accept()
                    self.log(f"TCP з'єднання від {a}")
                    threading.Thread(target=self.handle_tcp_client, args=(c, a), daemon=True).start()
                except socket.timeout:
                    continue
                except Exception as e:
                    if server_running:
                        self.log(f"TCP Accept помилка: {e}", "error")
        except Exception as e:
            self.log(f"TCP сервер помилка: {e}", "error")
    
    def handle_tcp_client(self, client_socket, addr):
        """Обробка TCP клієнта з покращеною перевіркою оплати"""
        global products, total, active, prev_products, tcp_log_file, receipt_formatter, last_total_sent
        buf = b""
        try:
            while server_running:
                try:
                    client_socket.settimeout(1.0)
                    d = client_socket.recv(1024)
                    if not d:
                        break
                    buf += d
                    
                    # Детальне логування
                    if tcp_log_file:
                        tcp_log_file.write("\n" + "="*60 + "\n")
                        tcp_log_file.write(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Від: {addr}\n")
                        tcp_log_file.write(f"RAW байти ({len(d)}): {d}\n")
                        tcp_log_file.write(f"HEX: {d.hex()}\n")
                        
                        # Пробуємо різні декодування
                        for encoding in ['cp1251', 'utf-8', 'cp1252', 'iso-8859-5']:
                            try:
                                decoded = d.decode(encoding, errors='ignore')
                                tcp_log_file.write(f"{encoding.upper()}: {decoded}\n")
                            except:
                                pass
                        tcp_log_file.flush()
                    
                    # Пробуємо декодувати з різними кодуваннями
                    text = ""
                    for encoding in ['cp1251', 'utf-8', 'cp1252']:
                        try:
                            text = buf.decode(encoding, errors='ignore')
                            break
                        except:
                            continue
                    
                    text_lower = text.lower()
                    
                    # ПОКРАЩЕНА ПЕРЕВІРКА УСПІШНОЇ ОПЛАТИ
                    success_patterns = [
                        "дякуємо за покупку",
                        "дякуємо за покупку",  # з іншою е
                        "дякуемо за покупку",  # без діакритики
                        "покупку",  # часткове співпадіння
                        "сплачено",
                        "оплачено"
                    ]
                    
                    payment_confirmed = False
                    for pattern in success_patterns:
                        if pattern in text_lower:
                            payment_confirmed = True
                            self.log(f"Патерн оплати знайдено: '{pattern}'", "info")
                            break
                    
                    # Перевірка по HEX патернах
                    hex_data = buf.hex().lower()
                    hex_patterns = [
                        "c4ffea",  # "Дяк" в CP1251
                        "d0b4d18f",  # "Дя" в UTF-8
                        "efeeea",  # "пок" в CP1251
                    ]
                    
                    for hex_pattern in hex_patterns:
                        if hex_pattern in hex_data:
                            payment_confirmed = True
                            self.log(f"HEX патерн оплати знайдено: {hex_pattern}", "info")
                            break
                    
                    # Перевірка повернення
                    if "повернення" in text_lower or "возврат" in text_lower:
                        self.log("ВИЯВЛЕНО ОПЕРАЦІЮ ПОВЕРНЕННЯ", "warning")
                        if products:
                            msg = receipt_formatter.format_return_receipt(products, total)
                            self.send_to_all_clients(msg)
                            self.log(f"ПОВЕРНЕННЯ ЗАВЕРШЕНО | Сума: {total} грн", "warning")
                        else:
                            msg = "=== ПОВЕРНЕННЯ ===\nПовернення виконано\n=== ОПЕРАЦІЮ СКАСОВАНО ===\n"
                            self.send_to_all_clients(msg)
                            self.log("ПОВЕРНЕННЯ БЕЗ ТОВАРІВ", "warning")
                        
                        # Очищення даних
                        products = {}
                        prev_products = {}
                        total = 0.0
                        active = False
                        last_total_sent = 0.0
                        data_processor.reset_transaction()
                        break
                    
                    # Перевірка успішної оплати
                    elif payment_confirmed and products:
                        self.log("ОПЛАТУ ПІДТВЕРДЖЕНО - Транзакція завершена!", "success")
                        self.log(f"Знайдений текст: '{text[:100]}'", "info")
                        
                        # Відправляємо фінальний чек
                        msg = "\n" + "="*40 + "\n"
                        msg += receipt_formatter.format_success_receipt(products, total)
                        msg += "\n" + "="*40 + "\n"
                        
                        self.send_to_all_clients(msg)
                        self.log(f"ТРАНЗАКЦІЮ ЗАВЕРШЕНО | Сума: {total} грн", "success")
                        
                        # ВАЖЛИВО: Очищення даних і встановлення active = False
                        products = {}
                        prev_products = {}
                        total = 0.0
                        active = False  # КРИТИЧНО: вимикаємо флаг активності!
                        last_total_sent = 0.0
                        data_processor.reset_transaction()
                        break
                    
                    # Логуємо, якщо не розпізнали
                    elif len(buf) > 0:
                        self.log(f"TCP дані не розпізнані: {text[:50]}", "warning")
                        
                except socket.timeout:
                    continue
                except Exception as e:
                    if server_running:
                        self.log(f"TCP клієнт помилка: {e}", "error")
                    break
                    
        except Exception as e:
            self.log(f"TCP обробка помилка: {e}", "error")
        finally:
            client_socket.close()
            self.log(f"TCP з'єднання закрито: {addr}")
    
    def client_server(self, port):
        """TCP сервер для клієнтських підключень"""
        global clients, cli_socket
        try:
            cli_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            cli_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            cli_socket.bind(("0.0.0.0", port))
            cli_socket.listen(10)
            self.log(f"Клієнтський сервер запущено на порту {port}", "success")
            
            while server_running:
                try:
                    cli_socket.settimeout(1.0)
                    c, a = cli_socket.accept()
                    self.log(f"КЛІЄНТ ПІДКЛЮЧЕНО: {a}", "info")
                    clients.append(c)
                    
                    # Відправка привітального повідомлення
                    try:
                        welcome_msg = "🔌 === UniPro POS Server v28 ===\n"
                        welcome_msg += "📡 Real-time оновлення увімкнено\n"
                        welcome_msg += "⏳ Очікування транзакції...\n"
                        welcome_msg += "="*40 + "\n"
                        c.send(welcome_msg.encode("utf-8"))
                    except:
                        pass
                        
                except socket.timeout:
                    continue
                except Exception as e:
                    if server_running:
                        self.log(f"Клієнтський сервер помилка: {e}", "error")
        except Exception as e:
            self.log(f"Клієнтський сервер помилка: {e}", "error")
    
    def apply_ports(self):
        """Застосування змінених портів і оновлення config.py"""
        try:
            # Валідація портів
            tcp_status = int(self.tcp_status_port.get())
            udp_json = int(self.udp_json_port.get())
            tcp_client = int(self.tcp_client_port.get())
            
            if not all(1024 <= p <= 65535 for p in [tcp_status, udp_json, tcp_client]):
                raise ValueError("Порти мають бути в діапазоні 1024-65535")
            
            # Перевірка на дублікати
            if len(set([tcp_status, udp_json, tcp_client])) != 3:
                raise ValueError("Порти мають бути унікальними")
            
            # Оновлення config.py
            self.update_config_py(tcp_status, udp_json, tcp_client)
            
            # Збереження в конфігурацію
            self.save_config()
            
            messagebox.showinfo("Успіх", "Порти успішно застосовано!\nПерезапустіть сервер для застосування змін.")
            
            # Якщо сервер працює, пропонуємо перезапуск
            if server_running:
                if messagebox.askyesno("Перезапуск", "Сервер працює. Перезапустити зараз?"):
                    self.stop_server()
                    self.root.after(500, self.start_server)
                    
        except ValueError as e:
            messagebox.showerror("Помилка", str(e))
        except Exception as e:
            messagebox.showerror("Помилка", f"Не вдалось застосувати порти: {e}")
    
    def update_config_py(self, tcp_status, udp_json, tcp_client):
        """Оновлення файлу config.py з новими портами"""
        config_content = f'''# Мережеві налаштування
TCP_STATUS_PORT = {tcp_status}    # TCP для статусів від принтера
UDP_JSON_PORT = {udp_json}      # UDP для JSON даних від принтера
TCP_CLIENT_PORT = {tcp_client}    # TCP для відправки клієнтам

# Кодування
ENCODINGS = ['utf-8', 'cp1251', 'ascii', 'latin1']

# Індикатори операцій
SUCCESS_INDICATORS = ["Дякуємо за покупку", "дякуємо за покупку", "покупку", "сплачено"]
RETURN_INDICATORS = ["Повернення", "повернення", "Возврат", "возврат"]
DELETE_INDICATORS = ["Видалено товар:", "видалено товар:"]

# HEX патерни для надійного визначення
SUCCESS_HEX_PATTERNS = ["c4ffea", "d0b4d18f", "efeeea"]
'''
        
        try:
            with open('config.py', 'w', encoding='utf-8') as f:
                f.write(config_content)
            self.log("config.py оновлено з новими портами", "success")
        except Exception as e:
            self.log(f"Помилка оновлення config.py: {e}", "error")
    
    def export_config_py(self):
        """Експорт поточних налаштувань в config.py"""
        try:
            tcp_status = int(self.tcp_status_port.get())
            udp_json = int(self.udp_json_port.get())
            tcp_client = int(self.tcp_client_port.get())
            
            self.update_config_py(tcp_status, udp_json, tcp_client)
            messagebox.showinfo("Успіх", "config.py успішно експортовано!")
        except Exception as e:
            messagebox.showerror("Помилка", f"Не вдалось експортувати config.py: {e}")
    
    def test_udp(self):
        """Відправка тестового UDP повідомлення"""
        test_data = {
            "cmd": {"cmd": ""},
            "goods": [
                {
                    "fPName": "Тестовий товар 1",
                    "fPrice": 15.50,
                    "fQtty": 2,
                    "fSum": 31.00
                },
                {
                    "fPName": "Тестовий товар 2",
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
            self.log("Тестове UDP повідомлення відправлено", "info")
            messagebox.showinfo("Тест UDP", "Тестове повідомлення відправлено успішно!")
        except Exception as e:
            self.log(f"Помилка відправки тестового повідомлення: {e}", "error")
            messagebox.showerror("Помилка", f"Не вдалось відправити тестове повідомлення: {e}")
    
    def test_tcp(self):
        """Тестування TCP з'єднання"""
        try:
            test_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            test_socket.settimeout(2)
            test_socket.connect(('localhost', int(self.tcp_status_port.get())))
            test_socket.send("Дякуємо за покупку".encode('cp1251'))
            test_socket.close()
            self.log("Тестове TCP повідомлення відправлено", "info")
            messagebox.showinfo("Тест TCP", "TCP тест виконано успішно!")
        except Exception as e:
            self.log(f"Помилка TCP тесту: {e}", "error")
            messagebox.showerror("Помилка", f"TCP тест не вдався: {e}")
    
    def check_windows_startup(self):
        """Перевірка наявності в автозавантаженні Windows"""
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
        """Додавання/видалення з автозавантаження Windows"""
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
                messagebox.showinfo("Успіх", "Програму додано в автозавантаження Windows")
            else:
                try:
                    winreg.DeleteValue(key, "UniProPOSServer")
                    messagebox.showinfo("Успіх", "Програму видалено з автозавантаження Windows")
                except:
                    pass
            
            winreg.CloseKey(key)
        except Exception as e:
            messagebox.showerror("Помилка", f"Не вдалось змінити автозавантаження: {e}")
            self.in_startup.set(not self.in_startup.get())
    
    def update_status(self):
        """Оновлення статусу в реальному часі"""
        global server_running, active, products, total, clients
        
        self.server_status.set("🟢 Працює" if server_running else "⭕ Зупинено")
        self.active_transaction.set("Так" if active else "Ні")
        
        # Правильний підрахунок товарів
        unique_items = len(products)
        total_units = sum(item.get('fQtty', 0) for item in products.values())
        self.cart_items.set(f"{unique_items} ({total_units} од.)")
        
        self.total_amount.set(f"{total:.2f} грн")
        self.connected_clients.set(str(len(clients)))
        
        # Оновлення кошика в моніторингу
        if products:
            cart_info = "=== ПОТОЧНИЙ КОШИК ===\n"
            for name, item in products.items():
                qty = item.get('fQtty', 0)
                price = item.get('fPrice', 0)
                sum_val = item.get('fSum', 0)
                cart_info += f"\n{name}\n  {qty} x {price:.2f} = {sum_val:.2f} грн\n"
            cart_info += f"\n{'='*30}\nРАЗОМ: {total:.2f} грн"
            
            self.cart_text.delete(1.0, END)
            self.cart_text.insert(END, cart_info)
        else:
            self.cart_text.delete(1.0, END)
            self.cart_text.insert(END, "Кошик порожній")
        
        # Оновлення статус бару
        if server_running:
            self.status_var.set(f"Сервер працює | Порти: TCP {self.tcp_status_port.get()}, "
                               f"UDP {self.udp_json_port.get()}, Клієнт {self.tcp_client_port.get()}")
        else:
            self.status_var.set("Сервер зупинено")
        
        # Повторний виклик через 1 секунду
        self.root.after(1000, self.update_status)
    
    def start_server(self):
        global server_running
        if server_running:
            self.log("Сервер вже працює", "warning")
            return
            
        try:
            tcp_status = int(self.tcp_status_port.get())
            udp_json = int(self.udp_json_port.get())
            tcp_client = int(self.tcp_client_port.get())
            
            if not all(1024 <= p <= 65535 for p in [tcp_status, udp_json, tcp_client]):
                raise ValueError("Порти мають бути в діапазоні 1024-65535")
            
            threading.Thread(target=self.udp_server, args=(udp_json,), daemon=True).start()
            threading.Thread(target=self.tcp_server, args=(tcp_status,), daemon=True).start()
            threading.Thread(target=self.client_server, args=(tcp_client,), daemon=True).start()
            
            server_running = True
            
            self.log(f"Сервер запущено на портах: TCP {tcp_status}, UDP {udp_json}, Клієнт {tcp_client}", "success")
            
            self.start_button.config(state=DISABLED)
            self.stop_button.config(state=NORMAL)
            
        except Exception as e:
            messagebox.showerror("Помилка", f"Не вдалось запустити сервер: {e}")
            self.log(f"Помилка запуску сервера: {e}", "error")
    
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
        
        self.log("Сервер зупинено", "warning")
        
        self.start_button.config(state=NORMAL)
        self.stop_button.config(state=DISABLED)
    
    def log(self, message, tag=None):
        """Покращене логування з тегами"""
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
        self.log("Логи очищено", "info")
    
    def clear_all_logs(self):
        if messagebox.askyesno("Підтвердження", "Очистити всі файли логів?"):
            self.clear_logs()
            try:
                for log_file in ['pos_server.log', 'tcp_server.log', 'tcp_4000.log']:
                    if os.path.exists(log_file):
                        os.remove(log_file)
                self.log("Всі файли логів очищено", "success")
            except Exception as e:
                self.log(f"Помилка очищення файлів логів: {e}", "error")
    
    def save_logs(self):
        from tkinter.filedialog import asksaveasfilename
        filename = asksaveasfilename(
            defaultextension=".log",
            filetypes=[("Файли логів", "*.log"), ("Текстові файли", "*.txt"), ("Всі файли", "*.*")]
        )
        if filename:
            try:
                with open(filename, 'w', encoding='utf-8') as f:
                    f.write(self.log_text.get(1.0, END))
                messagebox.showinfo("Успіх", "Логи збережено")
            except Exception as e:
                messagebox.showerror("Помилка", f"Не вдалось зберегти логи: {e}")
    
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
            self.log("Конфігурацію збережено", "success")
        except Exception as e:
            messagebox.showerror("Помилка", f"Не вдалось зберегти конфігурацію: {e}")
    
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
                self.log("Конфігурацію завантажено", "info")
        except Exception as e:
            self.log(f"Помилка завантаження конфігурації: {e}", "warning")
    
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
            item('Показати', self.show_window, default=True),
            item('Запустити сервер', lambda: self.root.after(0, self.start_server)),
            item('Зупинити сервер', lambda: self.root.after(0, self.stop_server)),
            pystray.Menu.SEPARATOR,
            item('Вихід', self.quit_from_tray)
        )
        
        self.tray_icon = pystray.Icon("pos_server", create_image(), "UniPro POS Server", menu)
    
    def on_closing(self):
        if self.minimize_to_tray.get() and TRAY_AVAILABLE:
            self.hide_window()
        else:
            if server_running:
                if messagebox.askyesno("Підтвердження", "Сервер працює. Зупинити і вийти?"):
                    self.quit_application()
            else:
                self.quit_application()
    
    def hide_window(self):
        self.root.withdraw()
        if self.tray_icon and not self.tray_icon.visible:
            threading.Thread(target=self.tray_icon.run, daemon=True).start()
        self.log("Програму згорнуто в трей", "info")
    
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
    print("UniPro POS Server v28")
    print("="*50)
    app = POSServerGUI()
    app.run()
