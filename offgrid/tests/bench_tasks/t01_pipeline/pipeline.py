# 初始存根 — agent 需要实现三个模块并让它们协作

class DataLoader:
    """从 CSV 字符串加载数据，返回 list[dict]"""
    def load(self, csv_text: str) -> list[dict]:
        pass


class DataTransformer:
    """接收 DataLoader 的输出，执行转换"""
    def __init__(self, loader: DataLoader):
        self.loader = loader

    def transform(self, csv_text: str, operations: list[dict]) -> list[dict]:
        """
        加载数据后按 operations 顺序执行转换。
        每个 operation 是 {"type": "filter"|"map"|"sort", ...}
        - filter: {"type": "filter", "field": str, "op": "eq"|"gt"|"lt"|"contains", "value": any}
        - map: {"type": "map", "field": str, "expr": str}  # expr 是 Python 表达式，变量 x 代表当前值
        - sort: {"type": "sort", "field": str, "reverse": bool}
        """
        pass


class PipelineValidator:
    """验证管道输出是否符合 schema"""
    def validate(self, data: list[dict], schema: dict) -> dict:
        """
        schema 格式: {"required_fields": [str], "types": {field: "int"|"float"|"str"}, "constraints": {field: {"min": v, "max": v}}}
        返回: {"valid": bool, "errors": [str]}
        """
        pass
