# 订单处理系统 — 所有逻辑塞在一个大函数里
# 任务：重构 process_order 函数，提取出至少 3 个有意义的子函数
# 要求：所有测试必须继续通过，不改变任何外部行为

class OrderProcessor:
    TAX_RATES = {"US": 0.08, "UK": 0.20, "DE": 0.19, "JP": 0.10, "CA": 0.13}
    SHIPPING_RATES = {"standard": 5.99, "express": 15.99, "overnight": 29.99}
    DISCOUNT_TIERS = [(500, 0.10), (200, 0.05), (100, 0.02)]  # (threshold, discount)

    def __init__(self):
        self.processed_orders = []

    def process_order(self, order: dict) -> dict:
        """
        处理订单，计算总价、税费、折扣、运费。
        order 格式: {
            "id": str,
            "items": [{"name": str, "price": float, "quantity": int}],
            "country": str,
            "shipping": str,  # "standard"|"express"|"overnight"
            "coupon": str | None,  # "SAVE10" = 10% off, "FLAT20" = $20 off
            "member": bool,  # 会员额外 5% 折扣
        }
        返回: {
            "id": str,
            "subtotal": float,
            "discount": float,
            "tax": float,
            "shipping": float,
            "total": float,
            "breakdown": list[str],  # 人类可读的费用明细
        }
        """
        # 计算小计
        subtotal = 0
        breakdown = []
        for item in order["items"]:
            item_total = item["price"] * item["quantity"]
            subtotal += item_total
            breakdown.append(f"{item['name']} x{item['quantity']}: ${item_total:.2f}")

        # 阶梯折扣
        tier_discount = 0
        for threshold, rate in self.DISCOUNT_TIERS:
            if subtotal >= threshold:
                tier_discount = subtotal * rate
                breakdown.append(f"Tier discount ({rate*100:.0f}%): -${tier_discount:.2f}")
                break

        # 优惠券
        coupon_discount = 0
        coupon = order.get("coupon")
        if coupon == "SAVE10":
            coupon_discount = subtotal * 0.10
            breakdown.append(f"Coupon SAVE10 (10%): -${coupon_discount:.2f}")
        elif coupon == "FLAT20":
            coupon_discount = min(20.0, subtotal)
            breakdown.append(f"Coupon FLAT20: -${coupon_discount:.2f}")

        # 会员折扣（在小计上计算，不叠加优惠券折扣）
        member_discount = 0
        if order.get("member"):
            member_discount = subtotal * 0.05
            breakdown.append(f"Member discount (5%): -${member_discount:.2f}")

        # 总折扣不能超过小计
        total_discount = tier_discount + coupon_discount + member_discount
        if total_discount > subtotal:
            total_discount = subtotal

        # 税费（在折扣后的金额上计算）
        after_discount = subtotal - total_discount
        country = order.get("country", "US")
        tax_rate = self.TAX_RATES.get(country, 0)
        tax = after_discount * tax_rate
        breakdown.append(f"Tax ({country} {tax_rate*100:.0f}%): ${tax:.2f}")

        # 运费（满 $100 免标准运费）
        shipping_type = order.get("shipping", "standard")
        shipping = self.SHIPPING_RATES.get(shipping_type, 5.99)
        if shipping_type == "standard" and after_discount >= 100:
            shipping = 0
            breakdown.append("Shipping: FREE (order over $100)")
        else:
            breakdown.append(f"Shipping ({shipping_type}): ${shipping:.2f}")

        total = after_discount + tax + shipping

        result = {
            "id": order["id"],
            "subtotal": round(subtotal, 2),
            "discount": round(total_discount, 2),
            "tax": round(tax, 2),
            "shipping": round(shipping, 2),
            "total": round(total, 2),
            "breakdown": breakdown,
        }

        self.processed_orders.append(result)
        return result

    def get_order(self, order_id: str) -> dict | None:
        for o in self.processed_orders:
            if o["id"] == order_id:
                return o
        return None

    def total_revenue(self) -> float:
        return round(sum(o["total"] for o in self.processed_orders), 2)
