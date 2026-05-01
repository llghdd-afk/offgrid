import pytest
from config_chain import DictSource, EnvSource, ConfigChain


class TestDictSource:
    def test_basic(self):
        src = DictSource({"a": 1, "b": "hello"})
        assert src.get_all() == {"a": 1, "b": "hello"}

    def test_nested(self):
        src = DictSource({"db": {"host": "localhost", "port": 5432}})
        result = src.get_all()
        assert result["db"]["host"] == "localhost"

    def test_empty(self):
        src = DictSource({})
        assert src.get_all() == {}


class TestEnvSource:
    def test_prefix_filter(self):
        env = {"APP_DB_HOST": "localhost", "APP_DB_PORT": "5432", "OTHER_KEY": "val"}
        src = EnvSource(prefix="APP_", env_dict=env)
        result = src.get_all()
        assert "db.host" in result
        assert "db.port" in result
        assert "other.key" not in result

    def test_key_transform(self):
        env = {"MYAPP_CACHE_TTL": "300", "MYAPP_LOG_LEVEL": "debug"}
        src = EnvSource(prefix="MYAPP_", env_dict=env)
        result = src.get_all()
        assert result["cache.ttl"] == "300"
        assert result["log.level"] == "debug"

    def test_no_prefix(self):
        env = {"HOST": "0.0.0.0", "PORT": "8080"}
        src = EnvSource(prefix="", env_dict=env)
        result = src.get_all()
        assert result["host"] == "0.0.0.0"
        assert result["port"] == "8080"


class TestConfigChainGet:
    def test_simple_get(self):
        chain = ConfigChain()
        chain.add_source(DictSource({"host": "localhost"}))
        assert chain.get("host") == "localhost"

    def test_default_value(self):
        chain = ConfigChain()
        chain.add_source(DictSource({"a": 1}))
        assert chain.get("missing", default="fallback") == "fallback"

    def test_nested_get(self):
        chain = ConfigChain()
        chain.add_source(DictSource({"db": {"host": "localhost", "port": 5432}}))
        assert chain.get("db.host") == "localhost"
        assert chain.get("db.port") == 5432

    def test_deep_nested(self):
        chain = ConfigChain()
        chain.add_source(DictSource({"a": {"b": {"c": {"d": 42}}}}))
        assert chain.get("a.b.c.d") == 42

    def test_cast_int(self):
        chain = ConfigChain()
        chain.add_source(DictSource({"port": "8080"}))
        assert chain.get("port", cast=int) == 8080

    def test_cast_float(self):
        chain = ConfigChain()
        chain.add_source(DictSource({"rate": "0.75"}))
        assert chain.get("rate", cast=float) == 0.75

    def test_cast_bool_true(self):
        chain = ConfigChain()
        chain.add_source(DictSource({"debug": "True", "verbose": "1", "enabled": "yes"}))
        assert chain.get("debug", cast=bool) is True
        assert chain.get("verbose", cast=bool) is True
        assert chain.get("enabled", cast=bool) is True

    def test_cast_bool_false(self):
        chain = ConfigChain()
        chain.add_source(DictSource({"debug": "false", "verbose": "0", "enabled": "NO"}))
        assert chain.get("debug", cast=bool) is False
        assert chain.get("verbose", cast=bool) is False
        assert chain.get("enabled", cast=bool) is False


class TestConfigChainPriority:
    def test_later_source_wins(self):
        chain = ConfigChain()
        chain.add_source(DictSource({"host": "default"}))
        chain.add_source(DictSource({"host": "override"}))
        assert chain.get("host") == "override"

    def test_three_layers(self):
        chain = ConfigChain()
        chain.add_source(DictSource({"a": 1, "b": 2, "c": 3}))
        chain.add_source(DictSource({"b": 20, "c": 30}))
        chain.add_source(DictSource({"c": 300}))
        assert chain.get("a") == 1
        assert chain.get("b") == 20
        assert chain.get("c") == 300

    def test_env_overrides_dict(self):
        chain = ConfigChain()
        chain.add_source(DictSource({"db": {"host": "localhost", "port": 5432}}))
        chain.add_source(EnvSource(prefix="APP_", env_dict={"APP_DB_HOST": "prod-server"}))
        assert chain.get("db.host") == "prod-server"
        assert chain.get("db.port") == 5432

    def test_chain_call(self):
        """链式调用"""
        chain = ConfigChain()
        result = chain.add_source(DictSource({"a": 1})).add_source(DictSource({"b": 2}))
        assert result is chain
        assert chain.get("a") == 1
        assert chain.get("b") == 2


class TestConfigChainSection:
    def test_get_section(self):
        chain = ConfigChain()
        chain.add_source(DictSource({
            "db": {"host": "localhost", "port": 5432},
            "cache": {"ttl": 300}
        }))
        section = chain.get_section("db")
        assert section == {"host": "localhost", "port": 5432}

    def test_section_with_override(self):
        chain = ConfigChain()
        chain.add_source(DictSource({"db": {"host": "localhost", "port": 5432}}))
        chain.add_source(EnvSource(prefix="APP_", env_dict={"APP_DB_HOST": "prod", "APP_DB_MAX_CONN": "100"}))
        section = chain.get_section("db")
        assert section["host"] == "prod"
        assert section["port"] == 5432
        assert section["max.conn"] == "100" or section.get("max_conn") == "100"


class TestConfigChainMerge:
    def test_merge_flat(self):
        chain = ConfigChain()
        chain.add_source(DictSource({"a": 1, "b": 2}))
        chain.add_source(DictSource({"b": 20, "c": 30}))
        merged = chain.merge_to_dict()
        assert merged == {"a": 1, "b": 20, "c": 30}

    def test_merge_nested(self):
        chain = ConfigChain()
        chain.add_source(DictSource({"db": {"host": "localhost", "port": 5432}}))
        chain.add_source(DictSource({"db": {"host": "prod"}, "cache": {"ttl": 60}}))
        merged = chain.merge_to_dict()
        assert merged["db"]["host"] == "prod"
        assert merged["db"]["port"] == 5432  # 保留未覆盖的
        assert merged["cache"]["ttl"] == 60

    def test_merge_env_into_nested(self):
        chain = ConfigChain()
        chain.add_source(DictSource({"db": {"host": "localhost"}}))
        chain.add_source(EnvSource(prefix="APP_", env_dict={"APP_DB_PORT": "3306"}))
        merged = chain.merge_to_dict()
        assert merged["db"]["host"] == "localhost"
        assert merged["db"]["port"] == "3306"
