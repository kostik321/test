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

# Настройки по умолчанию
DEFAULT_CONFIG = {
    'tcp_status_port': '4000',
    'udp_json_port': '4001', 
    'tcp_client_port': '4002',
    'autostart': 'true',
    'minimize_to_tray': 'true',
    'log_file': 'tcp_server.log'
}

class POSServerGUI:
    def __init__(self):
        self.root = Tk()
        self.root.title("UniPro POS Server v25")
        self.root.geometry("900x700")
        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)
        
        # Переменные для портов
        self.tcp_status_port = StringVar(value=DEFAULT_CONFIG['tcp_status_port'])
        self.udp_json_port = StringVar(value=DEFAULT_CONFIG['udp_json_port'])
        self.tcp_client_port = StringVar(value=DEFAULT_CONFIG['tcp_client_port'])
        self.autostart = BooleanVar(value=True)
        self.minimize_to_tray = BooleanVar(value=True)
        
        # Загрузка конфигурации
        self.load_config()
        
        # Создание интерфейса
        self.create_widgets()
        
        # Системный трей
        self.tray_icon = None
        if TRAY_AVAILABLE and self.minimize_to_tray.get():
            self.setup_tray()
        
        # Автозапуск
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
        file_menu.add_command(label="Выход", command=self.on_closing)
        
        # Notebook для вкладок
        notebook = ttk.Notebook(self.root)
        notebook.pack(fill=BOTH, expand=True, padx=10, pady=10)
        
        # Вкладка настроек
        settings_frame = ttk.Frame(notebook)
        notebook.add(settings_frame, text="Настройки")
        
        # Настройки портов
        ports_frame = ttk.LabelFrame(settings_frame, text="Настройки портов", padding=10)
        ports_frame.pack(fill=X, pady=5)
        
        ttk.Label(ports_frame, text="TCP порт для статусов принтера:").grid(row=0, column=0, sticky=W, pady=2)
        ttk.Entry(ports_frame, textvariable=self.tcp_status_port, width=10).grid(row=0, column=1, sticky=W, padx=5)
        
        ttk.Label(ports_frame, text="UDP порт для JSON данных:").grid(row=1, column=0, sticky=W, pady=2)
        ttk.Entry(ports_frame, textvariable=self.udp_json_port, width=10).grid(row=1, column=1, sticky=W, padx=5)
        
        ttk.Label(ports_frame, text="TCP порт для клиентов:").grid(row=2, column=0, sticky=W, pady=2)
        ttk.Entry(ports_frame, textvariable=self.tcp_client_port, width=10).grid(row=2, column=1, sticky=W, padx=5)
        
        # Настройки запуска
        startup_frame = ttk.LabelFrame(settings_frame, text="Настройки запуска", padding=10)
        startup_frame.pack(fill=X, pady=5)
        
        ttk.Checkbutton(startup_frame, text="Автозапуск сервера", variable=self.autostart).pack(anchor=W)
        ttk.Checkbutton(startup_frame, text="Сворачивать в системный трей", variable=self.minimize_to_tray).pack(anchor=W)
        
        # Кнопки управления
        control_frame = ttk.Frame(settings_frame)
        control_frame.pack(fill=X, pady=10)
        
        self.start_button = ttk.Button(control_frame, text="Запустить сервер", command=self.start_server)
        self.start_button.pack(side=LEFT, padx=5)
        
        self.stop_button = ttk.Button(control_frame, text="Остановить сервер", command=self.stop_server, state=DISABLED)
        self.stop_button.pack(side=LEFT, padx=5)
        
        ttk.Button(control_frame, text="Сохранить настройки", command=self.save_config).pack(side=LEFT, padx=5)
        ttk.Button(control_frame, text="Тестировать UDP", command=self.test_udp).pack(side=LEFT, padx=5)
        
        # Информационная панель
        info_frame = ttk.LabelFrame(settings_frame, text="Статус сервера", padding=10)
        info_frame.pack(fill=X, pady=5)
        
        self.server_status = StringVar(value="Остановлен")
        self.active_transaction = StringVar(value="Нет")
        self.cart_items = StringVar(value="0")
        self.total_amount = StringVar(value="0.00 UAH")
        
        ttk.Label(info_frame, text="Статус:").grid(row=0, column=0, sticky=W)
        ttk.Label(info_frame, textvariable=self.server_status).grid(row=0, column=1, sticky=W, padx=10)
        
        ttk.Label(info_frame, text="Активная транзакция:").grid(row=1, column=0, sticky=W)
        ttk.Label(info_frame, textvariable=self.active_transaction).grid(row=1, column=1, sticky=W, padx=10)
        
        ttk.Label(info_frame, text="Товаров в корзине:").grid(row=2, column=0, sticky=W)
        ttk.Label(info_frame, textvariable=self.cart_items).grid(row=2, column=1, sticky=W, padx=10)
        
        ttk.Label(info_frame, text="Сумма:").grid(row=3, column=0, sticky=W)
        ttk.Label(info_frame, textvariable=self.total_amount).grid(row=3, column=1, sticky=W, padx=10)
        
        # Вкладка логов
        log_frame = ttk.Frame(notebook)
        notebook.add(log_frame, text="Логи")
        
        # Область логов
        self.log_text = scrolledtext.ScrolledText(log_frame, height=30, width=100)
        self.log_text.pack(fill=BOTH, expand=True, padx=5, pady=5)
        
        # Кнопки для логов
        log_buttons = ttk.Frame(log_frame)
        log_buttons.pack(fill=X, padx=5, pady=5)
        
        ttk.Button(log_buttons, text="Очистить логи", command=self.clear_logs).pack(side=LEFT, padx=5)
        ttk.Button(log_buttons, text="Сохранить логи", command=self.save_logs).pack(side=LEFT, padx=5)
        
        # Статус бар
        self.status_var = StringVar(value="Сервер остановлен")
        status_bar = ttk.Label(self.root, textvariable=self.status_var, relief=SUNKEN)
        status_bar.pack(side=BOTTOM, fill=X)
        
        # Запуск обновления статуса
        self.update_status()
    
    def update_status(self):
        """Обновление статуса в реальном времени"""
        global server_running, active, products, total, clients
        
        self.server_status.set("Работает" if server_running else "Остановлен")
        self.active_transaction.set("Да" if active else "Нет")
        self.cart_items.set(str(len(products)))
        self.total_amount.set(f"{total:.2f} UAH")
        
        # Повторный вызов через 1 секунду
        self.root.after(1000, self.update_status)
    
    def setup_tray(self):
        if not TRAY_AVAILABLE:
            return
            
        # Создание иконки
        def create_image():
            width = 64
            height = 64
            image = Image.new('RGB', (width, height), color='blue')
            dc = ImageDraw.Draw(image)
            dc.rectangle([10, 10, width-10, height-10], fill='white')
            dc.text((15, 25), "POS", fill='blue')
            return image
        
        # Меню трея
        menu = pystray.Menu(
            item('Показать', self.show_window, default=True),
            item('Запустить сервер', self.start_server),
            item('Остановить сервер', self.stop_server),
            pystray.Menu.SEPARATOR,
            item('Выход', self.quit_application)
        )
        
        self.tray_icon = pystray.Icon("pos_server", create_image(), "UniPro POS Server", menu)
    
    def start_server(self):
        global server_running
        if server_running:
            return
            
        try:
            # Проверка портов
            tcp_status = int(self.tcp_status_port.get())
            udp_json = int(self.udp_json_port.get())
            tcp_client = int(self.tcp_client_port.get())
            
            if not (1024 <= tcp_status <= 65535 and 1024 <= udp_json <= 65535 and 1024 <= tcp_client <= 65535):
                raise ValueError("Порты должны быть в диапазоне 1024-65535")
            
            # Запуск серверов в отдельных потоках
            threading.Thread(target=self.udp_server, args=(udp_json,), daemon=True).start()
            threading.Thread(target=self.tcp_server, args=(tcp_status,), daemon=True).start()
            threading.Thread(target=self.client_server, args=(tcp_client,), daemon=True).start()
            
            server_running = True
            
            self.log(f"Сервер запущен на портах: TCP {tcp_status}, UDP {udp_json}, TCP Client {tcp_client}")
            self.status_var.set("Сервер работает")
            
            self.start_button.config(state=DISABLED)
            self.stop_button.config(state=NORMAL)
            
        except Exception as e:
            messagebox.showerror("Ошибка", f"Не удалось запустить сервер: {e}")
            self.log(f"Ошибка запуска сервера: {e}")
    
    def stop_server(self):
        global server_running, udp_socket, tcp_socket, cli_socket, tcp_log_file
        server_running = False
        
        # Закрытие сокетов
        try:
            if udp_socket:
                udp_socket.close()
            if tcp_socket:
                tcp_socket.close()
            if cli_socket:
                cli_socket.close()
            if tcp_log_file:
                tcp_log_file.close()
                tcp_log_file = None
        except:
            pass
        
        self.log("Сервер остановлен")
        self.status_var.set("Сервер остановлен")
        
        self.start_button.config(state=NORMAL)
        self.stop_button.config(state=DISABLED)
    
    def test_udp(self):
        """Отправка тестового UDP сообщения"""
        test_data = {
            "cmd": {"cmd": ""},
            "goods": [
                {
                    "fPName": "Тестовый товар",
                    "fPrice": 15.50,
                    "fQtty": 1,
                    "fSum": 15.50
                }
            ],
            "sum": {"sum": 15.50}
        }
        
        try:
            test_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            test_socket.sendto(json.dumps(test_data).encode(), ('localhost', int(self.udp_json_port.get())))
            test_socket.close()
            self.log("Тестовое UDP сообщение отправлено")
            messagebox.showinfo("Тест", "Тестовое UDP сообщение отправлено")
        except Exception as e:
            self.log(f"Ошибка отправки тестового сообщения: {e}")
            messagebox.showerror("Ошибка", f"Ошибка отправки тестового сообщения: {e}")
    
    def log(self, message):
        timestamp = datetime.now().strftime("[%H:%M:%S]")
        log_message = f"{timestamp} {message}\n"
        
        # Добавление в GUI
        self.log_text.insert(END, log_message)
        self.log_text.see(END)
        
        # Печать в консоль
        print(log_message.strip())
        
        # Сохранение в файл
        try:
            with open("pos_server.log", "a", encoding="utf-8") as f:
                f.write(log_message)
        except:
            pass
    
    def clear_logs(self):
        self.log_text.delete(1.0, END)
    
    def save_logs(self):
        from tkinter.filedialog import asksaveasfilename
        filename = asksaveasfilename(defaultextension=".log", filetypes=[("Log files", "*.log"), ("All files", "*.*")])
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
            'minimize_to_tray': str(self.minimize_to_tray.get())
        }
        
        try:
            with open('pos_server_config.ini', 'w') as f:
                config.write(f)
            messagebox.showinfo("Успех", "Конфигурация сохранена")
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
                self.autostart.set(settings.getboolean('autostart', True))
                self.minimize_to_tray.set(settings.getboolean('minimize_to_tray', True))
        except:
            pass  # Использовать значения по умолчанию
    
    def on_closing(self):
        if self.minimize_to_tray.get() and TRAY_AVAILABLE:
            self.hide_window()
        else:
            self.quit_application()
    
    def hide_window(self):
        self.root.withdraw()
        if self.tray_icon and not self.tray_icon.visible:
            threading.Thread(target=self.tray_icon.run, daemon=True).start()
    
    def show_window(self, icon=None, item=None):
        self.root.deiconify()
        self.root.lift()
        if self.tray_icon:
            self.tray_icon.stop()
    
    def quit_application(self, icon=None, item=None):
        self.stop_server()
        if self.tray_icon:
            self.tray_icon.stop()
        self.root.quit()
        self.root.destroy()
    
    def udp_server(self, port):
        global products, total, active, prev_products, udp_socket
        try:
            udp_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            udp_socket.bind(("0.0.0.0", port))
            self.log(f"UDP сервер запущен на порту {port}")
            
            while server_running:
                try:
                    udp_socket.settimeout(1.0)
                    data, addr = udp_socket.recvfrom(4096)
                    
                    obj = json.loads(data)
                    cmd = obj.get("cmd", {}).get("cmd", "")
                    
                    if cmd == "clear":
                        if active:
                            for c in clients:
                                try:
                                    c.send("=== ОПЕРАЦІЮ СКАСОВАНО ===\n".encode("utf-8"))
                                except:
                                    pass
                            self.log("TRANSACTION CANCELLED")
                        products = {}
                        prev_products = {}
                        total = 0.0
                        active = False
                    else:
                        old = dict(prev_products)
                        products = {}
                        prev_products = {}
                        
                        for item in obj.get("goods", []):
                            name = item.get("fPName", "")
                            if name:
                                products[name] = item
                                prev_products[name] = item
                        
                        if products and not active:
                            for c in clients:
                                try:
                                    c.send("ПОЧАТОК ОПЕРАЦІЇ\n".encode("utf-8"))
                                except:
                                    pass
                            active = True
                            self.log("NEW TRANSACTION STARTED")
                        
                        for name, item in products.items():
                            if name not in old:
                                price = item.get("fPrice", 0)
                                qty = item.get("fQtty", 0)
                                self.log(f"+ ADDED: {name} | {qty} x {price} UAH")
                        
                        for name in old:
                            if name not in products:
                                self.log(f"- REMOVED: {name}")
                        
                        total = obj.get("sum", {}).get("sum", 0)
                        if products:
                            self.log(f"CART: {len(products)} items | Total: {total} UAH")
                            
                except socket.timeout:
                    continue
                except Exception as e:
                    if server_running:
                        self.log(f"UDP Error: {e}")
        except Exception as e:
            self.log(f"UDP Server Error: {e}")
    
    def tcp_server(self, port):
        global products, total, clients, active, prev_products, tcp_socket, tcp_log_file
        try:
            tcp_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            tcp_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            tcp_socket.bind(("0.0.0.0", port))
            tcp_socket.listen(5)
            self.log(f"TCP сервер запущен на порту {port}")
            
            # Открытие файла логов
            try:
                tcp_log_file = open("tcp_server.log", "a", buffering=1, encoding="utf-8")
                self.log("TCP log file opened: tcp_server.log")
            except:
                self.log("Warning: Could not open TCP log file")
            
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
                        self.log(f"TCP Accept Error: {e}")
        except Exception as e:
            self.log(f"TCP Server Error: {e}")
    
    def handle_tcp_client(self, client_socket, addr):
        global products, total, active, prev_products, tcp_log_file
        buf = b""
        try:
            while server_running:
                try:
                    client_socket.settimeout(1.0)
                    d = client_socket.recv(1024)
                    if not d:
                        break
                    buf += d
                    
                    # Логирование в файл
                    if tcp_log_file:
                        tcp_log_file.write("\n" + "="*60 + "\n")
                        tcp_log_file.write(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] From: {addr}\n")
                        tcp_log_file.write(f"HEX: {d.hex()}\n")
                        tcp_log_file.write(f"CP1251: {d.decode('cp1251', errors='ignore')}\n")
                        tcp_log_file.write(f"UTF-8: {d.decode('utf-8', errors='ignore')}\n")
                        tcp_log_file.flush()
                    
                    text = buf.decode("cp1251", errors="ignore")
                    
                    # Проверка возврата
                    if "повернення" in text.lower() or "возврат" in text.lower():
                        self.log("RETURN OPERATION DETECTED")
                        if products:
                            msg = "=== ПОВЕРНЕННЯ ===\n"
                            for p in products.values():
                                n = p.get("fPName", "")
                                su = p.get("fSum", 0)
                                msg += f"ПОВЕРНУТО: {n}\nСума: {su} грн\n"
                                self.log(f"  RETURNED: {n} | {su} UAH")
                            msg += f"\nСУМА ПОВЕРНЕННЯ: {total} грн\n=== ОПЕРАЦІЮ СКАСОВАНО ===\n"
                            
                            for cl in clients:
                                try:
                                    cl.send(msg.encode("utf-8"))
                                except:
                                    pass
                            
                            self.log(f"RETURN COMPLETE | Total: {total} UAH")
                        else:
                            msg = "=== ПОВЕРНЕННЯ ===\nПовернення виконано\n=== ОПЕРАЦІЮ СКАСОВАНО ===\n"
                            for cl in clients:
                                try:
                                    cl.send(msg.encode("utf-8"))
                                except:
                                    pass
                            self.log("RETURN WITHOUT PRODUCTS")
                        
                        products = {}
                        prev_products = {}
                        total = 0.0
                        active = False
                        break
                    
                    # Проверка оплаты
                    elif "покупку" in text.lower() and products:
                        self.log("PAYMENT CONFIRMED")
                        msg = "=== ЧЕК ===\n"
                        for p in products.values():
                            n = p.get("fPName", "")
                            q = p.get("fQtty", 0)
                            pr = p.get("fPrice", 0)
                            su = p.get("fSum", 0)
                            msg += f"{n}\n{q} x {pr} = {su} грн\n"
                            self.log(f"  SOLD: {n} | {q} x {pr} = {su}")
                        msg += f"\nРАЗОМ: {total} грн\n=== СПЛАЧЕНО ===\nДякуємо за покупку!\n"
                        
                        for cl in clients:
                            try:
                                cl.send(msg.encode("utf-8"))
                            except:
                                pass
                        
                        self.log(f"TRANSACTION COMPLETE | Total: {total} UAH")
                        products = {}
                        prev_products = {}
                        total = 0.0
                        active = False
                        break
                        
                except socket.timeout:
                    continue
                except Exception as e:
                    if server_running:
                        self.log(f"TCP Client Error: {e}")
                    break
                    
        except Exception as e:
            self.log(f"TCP Handle Error: {e}")
        finally:
            client_socket.close()
    
    def client_server(self, port):
        global clients, cli_socket
        try:
            cli_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            cli_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            cli_socket.bind(("0.0.0.0", port))
            cli_socket.listen(5)
            self.log(f"Client сервер запущен на порту {port}")
            
            while server_running:
                try:
                    cli_socket.settimeout(1.0)
                    c, a = cli_socket.accept()
                    self.log(f"CLIENT CONNECTED: {a}")
                    clients.append(c)
                except socket.timeout:
                    continue
                except Exception as e:
                    if server_running:
                        self.log(f"Client Server Error: {e}")
        except Exception as e:
            self.log(f"Client Server Error: {e}")
    
    def run(self):
        self.root.mainloop()

if __name__ == "__main__":
    print("UniPro POS Server v25 with GUI and System Tray")
    app = POSServerGUI()
    app.run()
