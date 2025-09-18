class ReceiptFormatter:
    @staticmethod
    def format_success_receipt(products, total):
        """Форматирование чека продажи"""
        lines = ["=== ЧЕК ==="]
        
        for product in products.values():
            lines.append(product['full_name'])
            qty = product['qty']
            price = product['price']
            sum_val = product['sum']
            lines.append(f"{qty} x {price:.2f} = {sum_val:.2f} грн")
        
        lines.append("")
        lines.append(f"РАЗОМ: {total:.2f} грн")
        lines.append("=== СПЛАЧЕНО ===")
        lines.append("Дякуємо за покупку!")
        
        return "\n".join(lines)
    
    @staticmethod
    def format_return_receipt(products, total):
        """Форматирование чека возврата"""
        lines = ["=== ПОВЕРНЕННЯ ==="]
        
        for product in products.values():
            lines.append(f"ПОВЕРНУТО: {product['full_name']}")
            lines.append(f"Сума: {product['sum']:.2f} грн")
        
        lines.append("")
        lines.append(f"СУМА ПОВЕРНЕННЯ: {total:.2f} грн")
        lines.append("=== ОПЕРАЦІЮ СКАСОВАНО ===")
        
        return "\n".join(lines)
    
    @staticmethod
    def format_cancel_receipt():
        """Форматирование отмены"""
        return "=== ОПЕРАЦІЯ СКАСОВАНА ===\nКошик очищено"
