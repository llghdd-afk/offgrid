# 配置系统：支持多层继承、环境变量覆盖、类型转换
# agent 需要实现三个类协作

class ConfigSource:
    """配置源基类"""
    def get_all(self) -> dict:
        pass


class DictSource(ConfigSource):
    """从 dict 加载配置"""
    def __init__(self, data: dict):
        pass

    def get_all(self) -> dict:
        pass


class EnvSource(ConfigSource):
    """从环境变量加载配置，支持前缀过滤和 key 转换
    例如 APP_DB_HOST -> db.host (前缀 APP_, 下划线转点号, 小写)
    """
    def __init__(self, prefix: str = "", env_dict: dict = None):
        pass

    def get_all(self) -> dict:
        pass


class ConfigChain:
    """多层配置链，后加的 source 优先级更高。支持嵌套 key 访问。"""

    def __init__(self):
        pass

    def add_source(self, source: ConfigSource) -> "ConfigChain":
        """添加配置源，后添加的优先级更高。返回 self 支持链式调用。"""
        pass

    def get(self, key: str, default=None, cast=None):
        """
        获取配置值。
        - key: 支持点号分隔的嵌套访问，如 "db.host"
        - default: key 不存在时的默认值
        - cast: 类型转换函数，如 int, float, bool
        - bool 转换规则: "true"/"1"/"yes" -> True, "false"/"0"/"no" -> False (不区分大小写)
        """
        pass

    def get_section(self, prefix: str) -> dict:
        """获取某个前缀下的所有配置，返回去掉前缀后的 flat dict。
        例如 prefix="db" 返回 {"host": "...", "port": "..."}
        """
        pass

    def merge_to_dict(self) -> dict:
        """合并所有 source，返回嵌套 dict。后添加的 source 覆盖先添加的。"""
        pass
