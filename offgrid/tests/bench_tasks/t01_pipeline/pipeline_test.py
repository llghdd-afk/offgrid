import pytest
from pipeline import DataLoader, DataTransformer, PipelineValidator


# ── DataLoader 测试 ──

class TestDataLoader:
    def test_basic_load(self):
        loader = DataLoader()
        csv = "name,age,city\nAlice,30,NYC\nBob,25,LA"
        result = loader.load(csv)
        assert len(result) == 2
        assert result[0] == {"name": "Alice", "age": "30", "city": "NYC"}
        assert result[1] == {"name": "Bob", "age": "25", "city": "LA"}

    def test_empty_csv(self):
        loader = DataLoader()
        result = loader.load("name,age\n")
        assert result == []

    def test_header_only(self):
        loader = DataLoader()
        result = loader.load("name,age")
        assert result == []

    def test_whitespace_handling(self):
        loader = DataLoader()
        csv = "name, age ,city\n Alice , 30 , NYC "
        result = loader.load(csv)
        assert result[0] == {"name": "Alice", "age": "30", "city": "NYC"}

    def test_quoted_fields(self):
        loader = DataLoader()
        csv = 'name,desc\nAlice,"hello, world"\nBob,"say ""hi"""'
        result = loader.load(csv)
        assert result[0]["desc"] == "hello, world"
        assert result[1]["desc"] == 'say "hi"'


# ── DataTransformer 测试 (依赖 DataLoader 正确) ──

class TestDataTransformer:
    def setup_method(self):
        self.loader = DataLoader()
        self.transformer = DataTransformer(self.loader)
        self.csv = "name,age,salary\nAlice,30,50000\nBob,25,60000\nCharlie,35,45000"

    def test_filter_eq(self):
        ops = [{"type": "filter", "field": "name", "op": "eq", "value": "Alice"}]
        result = self.transformer.transform(self.csv, ops)
        assert len(result) == 1
        assert result[0]["name"] == "Alice"

    def test_filter_gt(self):
        ops = [{"type": "filter", "field": "age", "op": "gt", "value": 28}]
        result = self.transformer.transform(self.csv, ops)
        assert len(result) == 2
        names = [r["name"] for r in result]
        assert "Alice" in names and "Charlie" in names

    def test_filter_lt(self):
        ops = [{"type": "filter", "field": "salary", "op": "lt", "value": 55000}]
        result = self.transformer.transform(self.csv, ops)
        assert len(result) == 2

    def test_filter_contains(self):
        ops = [{"type": "filter", "field": "name", "op": "contains", "value": "li"}]
        result = self.transformer.transform(self.csv, ops)
        assert len(result) == 2  # Alice, Charlie

    def test_map_expression(self):
        ops = [{"type": "map", "field": "age", "expr": "int(x) + 1"}]
        result = self.transformer.transform(self.csv, ops)
        assert result[0]["age"] == 31
        assert result[1]["age"] == 26

    def test_sort_ascending(self):
        ops = [{"type": "sort", "field": "age", "reverse": False}]
        result = self.transformer.transform(self.csv, ops)
        ages = [int(r["age"]) if isinstance(r["age"], str) else r["age"] for r in result]
        assert ages == [25, 30, 35]

    def test_sort_descending(self):
        ops = [{"type": "sort", "field": "salary", "reverse": True}]
        result = self.transformer.transform(self.csv, ops)
        names = [r["name"] for r in result]
        assert names[0] == "Bob"  # highest salary

    def test_chained_operations(self):
        """filter -> map -> sort 链式操作"""
        ops = [
            {"type": "filter", "field": "age", "op": "gt", "value": 24},
            {"type": "map", "field": "salary", "expr": "int(x) * 1.1"},
            {"type": "sort", "field": "salary", "reverse": True},
        ]
        result = self.transformer.transform(self.csv, ops)
        assert len(result) == 3
        # salary 应该被乘以 1.1 并降序排列
        salaries = [r["salary"] for r in result]
        assert salaries == sorted(salaries, reverse=True)
        assert abs(salaries[0] - 66000.0) < 0.01  # Bob: 60000 * 1.1

    def test_empty_operations(self):
        result = self.transformer.transform(self.csv, [])
        assert len(result) == 3


# ── PipelineValidator 测试 (依赖 DataLoader + DataTransformer 正确) ──

class TestPipelineValidator:
    def setup_method(self):
        self.validator = PipelineValidator()

    def test_valid_data(self):
        data = [{"name": "Alice", "age": 30}]
        schema = {
            "required_fields": ["name", "age"],
            "types": {"age": "int"},
            "constraints": {}
        }
        result = self.validator.validate(data, schema)
        assert result["valid"] is True
        assert result["errors"] == []

    def test_missing_field(self):
        data = [{"name": "Alice"}]
        schema = {
            "required_fields": ["name", "age"],
            "types": {},
            "constraints": {}
        }
        result = self.validator.validate(data, schema)
        assert result["valid"] is False
        assert any("age" in e for e in result["errors"])

    def test_type_check_int(self):
        data = [{"name": "Alice", "age": "not_a_number"}]
        schema = {
            "required_fields": ["name"],
            "types": {"age": "int"},
            "constraints": {}
        }
        result = self.validator.validate(data, schema)
        assert result["valid"] is False

    def test_type_check_float(self):
        data = [{"score": 3.14}]
        schema = {
            "required_fields": [],
            "types": {"score": "float"},
            "constraints": {}
        }
        result = self.validator.validate(data, schema)
        assert result["valid"] is True

    def test_constraint_min_max(self):
        data = [{"age": 15}, {"age": 30}]
        schema = {
            "required_fields": [],
            "types": {"age": "int"},
            "constraints": {"age": {"min": 18, "max": 65}}
        }
        result = self.validator.validate(data, schema)
        assert result["valid"] is False
        assert any("15" in e or "min" in e.lower() for e in result["errors"])

    def test_end_to_end_pipeline(self):
        """完整管道: load -> transform -> validate"""
        loader = DataLoader()
        transformer = DataTransformer(loader)
        csv = "name,age,score\nAlice,30,85\nBob,25,92\nCharlie,17,78"

        ops = [
            {"type": "filter", "field": "age", "op": "gt", "value": 18},
            {"type": "map", "field": "score", "expr": "int(x) / 100.0"},
        ]
        data = transformer.transform(csv, ops)

        schema = {
            "required_fields": ["name", "age", "score"],
            "types": {"score": "float"},
            "constraints": {"score": {"min": 0.0, "max": 1.0}}
        }
        result = self.validator.validate(data, schema)
        assert result["valid"] is True
        assert len(data) == 2  # Charlie filtered out (age 17)
