class ReceiptFormatter:
    @staticmethod
    def format_success_receipt(products, total):
        """Форматування чека продажу з правильним підрахунком кількості"""
        lines = ["=== ЧЕК ==="]
        
        for product in products.values():
            # Використовуємо правильні ключі з JSON
            name = product.get('fPName', 'Невідомий товар')
            original_qty = product.get('fQtty', 1)
            price = product.get('fPrice', 0)
            sum_val = product.get('fSum', 0)
            
            # ВАЖЛИВО: Вираховуємо реальну кількість через ділення
            if price > 0:
                # Використовуємо int() для точного цілочисельного результату
                real_qty = int(sum_val / price + 0.5)  # Ділимо суму на ціну з округленням
            else:
                real_qty = original_qty
            
            lines.append(name)
            lines.append(f"{real_qty} x {price:.2f} = {sum_val:.2f} грн")
        
        lines.append("")
        lines.append(f"РАЗОМ: {total:.2f} грн")
        lines.append("=== СПЛАЧЕНО ===")
        lines.append("Дякуємо за покупку!")
        
        return "\n".join(lines)
    
    @staticmethod
    def format_return_receipt(products, total):
        """Форматування чека повернення з правильним підрахунком кількості"""
        lines = ["=== ПОВЕРНЕННЯ ==="]
        
        for product in products.values():
            name = product.get('fPName', 'Невідомий товар')
            qty = product.get('fQtty', 0)
            price = product.get('fPrice', 0)
            sum_val = product.get('fSum', 0)
            
            # ВАЖЛИВО: Вираховуємо реальну кількість через ділення
            if price > 0:
                real_qty = round(sum_val / price)  # Ділимо суму на ціну
            else:
                real_qty = qty
            
            lines.append(f"ПОВЕРНУТО: {name}")
            lines.append(f"Кількість: {real_qty} x {price:.2f} грн")
            lines.append(f"Сума: {sum_val:.2f} грн")
        
        lines.append("")
        lines.append(f"СУМА ПОВЕРНЕННЯ: {total:.2f} грн")
        lines.append("=== ОПЕРАЦІЮ СКАСОВАНО ===")
        
        return "\n".join(lines)
    
    @staticmethod
    def format_cancel_receipt():
        """Форматування скасування"""
        return "=== ОПЕРАЦІЯ СКАСОВАНА ===\nКошик очищено"
