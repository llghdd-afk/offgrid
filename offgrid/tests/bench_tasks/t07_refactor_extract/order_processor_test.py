import pytest
from order_processor import OrderProcessor


@pytest.fixture
def processor():
    return OrderProcessor()


def make_order(**kwargs):
    base = {
        "id": "ORD-001",
        "items": [{"name": "Widget", "price": 25.0, "quantity": 2}],
        "country": "US",
        "shipping": "standard",
        "coupon": None,
        "member": False,
    }
    base.update(kwargs)
    return base


class TestSubtotal:
    def test_single_item(self, processor):
        order = make_order(items=[{"name": "A", "price": 10.0, "quantity": 1}])
        result = processor.process_order(order)
        assert result["subtotal"] == 10.0

    def test_multiple_items(self, processor):
        order = make_order(items=[
            {"name": "A", "price": 10.0, "quantity": 2},
            {"name": "B", "price": 5.0, "quantity": 3},
        ])
        result = processor.process_order(order)
        assert result["subtotal"] == 35.0

    def test_quantity(self, processor):
        order = make_order(items=[{"name": "A", "price": 7.5, "quantity": 4}])
        result = processor.process_order(order)
        assert result["subtotal"] == 30.0


class TestTierDiscount:
    def test_no_discount_under_100(self, processor):
        order = make_order(items=[{"name": "A", "price": 30.0, "quantity": 1}])
        result = processor.process_order(order)
        assert result["discount"] == 0.0

    def test_2_percent_at_100(self, processor):
        order = make_order(items=[{"name": "A", "price": 100.0, "quantity": 1}])
        result = processor.process_order(order)
        assert result["discount"] == 2.0  # 100 * 0.02

    def test_5_percent_at_200(self, processor):
        order = make_order(items=[{"name": "A", "price": 200.0, "quantity": 1}])
        result = processor.process_order(order)
        assert result["discount"] == 10.0  # 200 * 0.05

    def test_10_percent_at_500(self, processor):
        order = make_order(items=[{"name": "A", "price": 500.0, "quantity": 1}])
        result = processor.process_order(order)
        assert result["discount"] == 50.0  # 500 * 0.10


class TestCoupons:
    def test_save10(self, processor):
        order = make_order(
            items=[{"name": "A", "price": 80.0, "quantity": 1}],
            coupon="SAVE10"
        )
        result = processor.process_order(order)
        assert result["discount"] == 8.0  # 80 * 0.10

    def test_flat20(self, processor):
        order = make_order(
            items=[{"name": "A", "price": 80.0, "quantity": 1}],
            coupon="FLAT20"
        )
        result = processor.process_order(order)
        assert result["discount"] == 20.0

    def test_flat20_cap(self, processor):
        """FLAT20 不能超过小计"""
        order = make_order(
            items=[{"name": "A", "price": 15.0, "quantity": 1}],
            coupon="FLAT20"
        )
        result = processor.process_order(order)
        assert result["discount"] == 15.0

    def test_no_coupon(self, processor):
        order = make_order(coupon=None)
        result = processor.process_order(order)
        # only tier discount if applicable
        assert result["discount"] >= 0


class TestMemberDiscount:
    def test_member_5_percent(self, processor):
        order = make_order(
            items=[{"name": "A", "price": 80.0, "quantity": 1}],
            member=True
        )
        result = processor.process_order(order)
        assert result["discount"] == 4.0  # 80 * 0.05

    def test_member_plus_coupon(self, processor):
        order = make_order(
            items=[{"name": "A", "price": 80.0, "quantity": 1}],
            member=True,
            coupon="SAVE10"
        )
        result = processor.process_order(order)
        # member 5% + coupon 10% = 12.0
        assert result["discount"] == 12.0

    def test_discount_cap(self, processor):
        """总折扣不能超过小计"""
        order = make_order(
            items=[{"name": "A", "price": 10.0, "quantity": 1}],
            member=True,
            coupon="FLAT20"
        )
        result = processor.process_order(order)
        assert result["discount"] == 10.0  # capped at subtotal
        assert result["total"] >= 0


class TestTax:
    def test_us_tax(self, processor):
        order = make_order(
            items=[{"name": "A", "price": 100.0, "quantity": 1}],
            country="US"
        )
        result = processor.process_order(order)
        # subtotal=100, discount=2% tier=2, after=98, tax=98*0.08=7.84
        assert result["tax"] == 7.84

    def test_uk_tax(self, processor):
        order = make_order(
            items=[{"name": "A", "price": 50.0, "quantity": 1}],
            country="UK"
        )
        result = processor.process_order(order)
        assert result["tax"] == 10.0  # 50 * 0.20

    def test_unknown_country_no_tax(self, processor):
        order = make_order(
            items=[{"name": "A", "price": 50.0, "quantity": 1}],
            country="ZZ"
        )
        result = processor.process_order(order)
        assert result["tax"] == 0.0


class TestShipping:
    def test_standard_shipping(self, processor):
        order = make_order(
            items=[{"name": "A", "price": 30.0, "quantity": 1}],
            shipping="standard"
        )
        result = processor.process_order(order)
        assert result["shipping"] == 5.99

    def test_express_shipping(self, processor):
        order = make_order(shipping="express")
        result = processor.process_order(order)
        assert result["shipping"] == 15.99

    def test_free_standard_over_100(self, processor):
        order = make_order(
            items=[{"name": "A", "price": 150.0, "quantity": 1}],
            shipping="standard"
        )
        result = processor.process_order(order)
        assert result["shipping"] == 0.0

    def test_express_not_free_over_100(self, processor):
        order = make_order(
            items=[{"name": "A", "price": 150.0, "quantity": 1}],
            shipping="express"
        )
        result = processor.process_order(order)
        assert result["shipping"] == 15.99


class TestTotal:
    def test_total_calculation(self, processor):
        order = make_order(
            items=[{"name": "A", "price": 50.0, "quantity": 1}],
            country="US",
            shipping="standard"
        )
        result = processor.process_order(order)
        expected = 50.0 + (50.0 * 0.08) + 5.99  # no discount
        assert result["total"] == round(expected, 2)

    def test_breakdown_not_empty(self, processor):
        order = make_order()
        result = processor.process_order(order)
        assert len(result["breakdown"]) > 0
        assert any("$" in line for line in result["breakdown"])


class TestRefactoring:
    """验证重构后的代码结构"""

    def test_process_order_calls_subfunctions(self, processor):
        """process_order 应该调用至少 3 个子函数"""
        import inspect
        source = inspect.getsource(OrderProcessor.process_order)
        # 统计 self.xxx() 调用（排除 self.processed_orders 等属性访问）
        import re
        method_calls = re.findall(r'self\.(\w+)\(', source)
        # 排除已有的方法
        existing = {'get_order', 'total_revenue', 'process_order'}
        new_methods = [m for m in set(method_calls) if m not in existing
                       and not m.startswith('_') or m.startswith('_calc') or m.startswith('_apply')]
        assert len(set(method_calls) - existing) >= 3, \
            f"process_order should call at least 3 extracted methods, found: {set(method_calls) - existing}"

    def test_process_order_shorter(self, processor):
        """重构后 process_order 应该更短"""
        import inspect
        source = inspect.getsource(OrderProcessor.process_order)
        lines = [l for l in source.split('\n') if l.strip() and not l.strip().startswith('#')]
        assert len(lines) <= 35, f"process_order should be <=35 lines after refactoring, got {len(lines)}"


class TestStateManagement:
    def test_get_order(self, processor):
        order = make_order(id="ORD-123")
        processor.process_order(order)
        assert processor.get_order("ORD-123") is not None
        assert processor.get_order("ORD-999") is None

    def test_total_revenue(self, processor):
        processor.process_order(make_order(id="1", items=[{"name": "A", "price": 50.0, "quantity": 1}]))
        processor.process_order(make_order(id="2", items=[{"name": "B", "price": 30.0, "quantity": 1}]))
        assert processor.total_revenue() > 0

    def test_multiple_orders(self, processor):
        for i in range(5):
            processor.process_order(make_order(id=f"ORD-{i}"))
        assert len(processor.processed_orders) == 5
