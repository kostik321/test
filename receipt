class ReceiptFormatter:
    @staticmethod
    def format_success_receipt(products, total):
        """Форматування чека продажу"""
        lines = ["=== ЧЕК ==="]
        
        for product in products.values():
            # Используем правильные ключи из JSON
            name = product.get('fPName', 'Невідомий товар')
            qty = product.get('fQtty', 0)
            price = product.get('fPrice', 0)
            sum_val = product.get('fSum', 0)
            lines.append(name)
            lines.append(f"{qty} x {price:.2f} = {sum_val:.2f} грн")
        
        lines.append("")
        lines.append(f"РАЗОМ: {total:.2f} грн")
        lines.append("=== СПЛАЧЕНО ===")
        lines.append("Дякуємо за покупку!")
        
        return "\n".join(lines)
    
    @staticmethod
    def format_return_receipt(products, total):
        """Форматування чека повернення"""
        lines = ["=== ПОВЕРНЕННЯ ==="]
        
        for product in products.values():
            name = product.get('fPName', 'Невідомий товар')
            sum_val = product.get('fSum', 0)
            lines.append(f"ПОВЕРНУТО: {name}")
            lines.append(f"Сума: {sum_val:.2f} грн")
        
        lines.append("")
        lines.append(f"СУМА ПОВЕРНЕННЯ: {total:.2f} грн")
        lines.append("=== ОПЕРАЦІЮ СКАСОВАНО ===")
        
        return "\n".join(lines)
    
    @staticmethod
    def format_cancel_receipt():
        """Форматування скасування"""
        return "=== ОПЕРАЦІЯ СКАСОВАНА ===\nКошик очищено"
