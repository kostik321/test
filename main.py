#!/usr/bin/env python3
import socket
import threading
import json
import time
from datetime import datetime

print("POS Server v25 with TCP logging")

products = {}
total = 0.0
clients = []
active = False
prev_products = {}

# Открываем файл для логирования TCP
tcp_log_file = None
try:
    tcp_log_file = open("/app/tcp_4000.log", "a", buffering=1)
    print("TCP log file opened: /app/tcp_4000.log")
except:
    print("Warning: Could not open TCP log file")

def log(msg):
    print("[" + datetime.now().strftime("%H:%M:%S") + "] " + msg)

def udp():
    global products, total, active, prev_products
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.bind(("0.0.0.0", 4001))
    log("UDP 4001 started")
    while True:
        data, addr = s.recvfrom(4096)
        try:
            obj = json.loads(data)
            cmd = obj.get("cmd", {}).get("cmd", "")
            if cmd == "clear":
                if active:
                    for c in clients:
                        try:
                            c.send("=== ОПЕРАЦІЮ СКАСОВАНО ===\n".encode("utf-8"))
                        except:
                            pass
                    log("TRANSACTION CANCELLED")
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
                    log("NEW TRANSACTION STARTED")
                
                for name, item in products.items():
                    if name not in old:
                        price = item.get("fPrice", 0)
                        qty = item.get("fQtty", 0)
                        log("+ ADDED: " + name + " | " + str(qty) + " x " + str(price) + " UAH")
                
                for name in old:
                    if name not in products:
                        log("- REMOVED: " + name)
                
                total = obj.get("sum", {}).get("sum", 0)
                if products:
                    log("CART: " + str(len(products)) + " items | Total: " + str(total) + " UAH")
        except Exception as e:
            log("Error: " + str(e))

def tcp():
    global products, total, clients, active, prev_products, tcp_log_file
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    s.bind(("0.0.0.0", 4000))
    s.listen(5)
    log("TCP 4000 started")
    while True:
        c, a = s.accept()
        log("TCP connection from " + str(a))
        buf = b""
        try:
            while True:
                d = c.recv(1024)
                if not d:
                    break
                buf += d
                
                # Логирование в файл
                if tcp_log_file:
                    tcp_log_file.write("\n" + "="*60 + "\n")
                    tcp_log_file.write("[" + datetime.now().strftime("%Y-%m-%d %H:%M:%S") + "] From: " + str(a) + "\n")
                    tcp_log_file.write("HEX: " + d.hex() + "\n")
                    tcp_log_file.write("CP1251: " + d.decode("cp1251", errors="ignore") + "\n")
                    tcp_log_file.write("UTF-8: " + d.decode("utf-8", errors="ignore") + "\n")
                    tcp_log_file.write("RAW ASCII: " + str([chr(b) if 32 <= b <= 126 else f"[{b}]" for b in d]) + "\n")
                    tcp_log_file.flush()
                
                text = buf.decode("cp1251", errors="ignore")
                
                # Проверка возврата
                if "повернення" in text.lower() or "возврат" in text.lower():
                    log("RETURN OPERATION DETECTED")
                    if products:
                        msg = "=== ПОВЕРНЕННЯ ===\n"
                        for p in products.values():
                            n = p.get("fPName", "")
                            su = p.get("fSum", 0)
                            msg += "ПОВЕРНУТО: " + n + "\n"
                            msg += "Сума: " + str(su) + " грн\n"
                            log("  RETURNED: " + n + " | " + str(su) + " UAH")
                        msg += "\nСУМА ПОВЕРНЕННЯ: " + str(total) + " грн\n"
                        msg += "=== ОПЕРАЦІЮ СКАСОВАНО ===\n"
                        
                        for cl in clients:
                            try:
                                cl.send(msg.encode("utf-8"))
                            except:
                                pass
                        
                        log("RETURN COMPLETE | Total: " + str(total) + " UAH")
                    else:
                        msg = "=== ПОВЕРНЕННЯ ===\n"
                        msg += "Повернення виконано\n"
                        msg += "=== ОПЕРАЦІЮ СКАСОВАНО ===\n"
                        for cl in clients:
                            try:
                                cl.send(msg.encode("utf-8"))
                            except:
                                pass
                        log("RETURN WITHOUT PRODUCTS")
                    
                    products = {}
                    prev_products = {}
                    total = 0.0
                    active = False
                    break
                
                # Проверка оплаты
                elif "покупку" in text.lower() and products:
                    log("PAYMENT CONFIRMED")
                    msg = "=== ЧЕК ===\n"
                    for p in products.values():
                        n = p.get("fPName", "")
                        q = p.get("fQtty", 0)
                        pr = p.get("fPrice", 0)
                        su = p.get("fSum", 0)
                        msg += n + "\n"
                        msg += str(q) + " x " + str(pr) + " = " + str(su) + " грн\n"
                        log("  SOLD: " + n + " | " + str(q) + " x " + str(pr) + " = " + str(su))
                    msg += "\nРАЗОМ: " + str(total) + " грн\n"
                    msg += "=== СПЛАЧЕНО ===\n"
                    msg += "Дякуємо за покупку!\n"
                    
                    for cl in clients:
                        try:
                            cl.send(msg.encode("utf-8"))
                        except:
                            pass
                    
                    log("TRANSACTION COMPLETE | Total: " + str(total) + " UAH")
                    products = {}
                    prev_products = {}
                    total = 0.0
                    active = False
                    break
                    
        except Exception as e:
            log("TCP Error: " + str(e))
        c.close()

def cli():
    global clients
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    s.bind(("0.0.0.0", 4002))
    s.listen(5)
    log("Client server 4002 started")
    while True:
        c, a = s.accept()
        log("CLIENT CONNECTED: " + str(a))
        clients.append(c)

threading.Thread(target=udp, daemon=True).start()
threading.Thread(target=tcp, daemon=True).start()
threading.Thread(target=cli, daemon=True).start()

log("SERVER READY")

while True:
    time.sleep(60)