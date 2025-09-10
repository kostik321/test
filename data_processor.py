import re
import json

class DataProcessor:
    def __init__(self):
        self.json_products = {}
        self.current_transaction_lines = []
        self.transaction_total = 0.0
        self.transaction_active = False
        self.is_return_operation = False
        
    def process_json_data(self, json_obj):
        """Обработка JSON данных от принтера"""
        cmd = json_obj.get('cmd', {}).get('cmd', '')
        
        if cmd == 'clear':
            print("JSON команда очистки")
            return 'CLEAR'
            
        # Сохраняем товары
        goods = json_obj.get('goods', [])
        for item in goods:
            full_name = item.get('fPName', '')
            if full_name:
                short_name = self.create_short_name(full_name)
                self.json_products[short_name] = {
                    'full_name': full_name,
                    'price': item.get('fPrice', 0),
                    'qty': item.get('fQtty', 0),
                    'sum': item.get('fSum', 0)
                }
                print(f"Сохранен товар: '{full_name}'")
        
        self.transaction_total = json_obj.get('sum', {}).get('sum', 0)
        return None
    
    def create_short_name(self, full_name):
        """Создание короткого ключа для сопоставления"""
        short = re.sub(r'[^\w\sа-яёіїєґ]', '', full_name.lower(), flags=re.IGNORECASE)
        short = re.sub(r'\s+', ' ', short).strip()
        return short[:30]  # Ограничиваем длину
    
    def reset_transaction(self):
        """Полный сброс транзакции"""
        self.transaction_active = False
        self.current_transaction_lines = []
        self.transaction_total = 0.0
        self.is_return_operation = False
        self.json_products = {}  # ВАЖНО: очищаем словарь товаров!
        print("Транзакция сброшена, все данные очищены")
