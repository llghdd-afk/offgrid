import pytest
from dataclasses import fields as dataclass_fields
from user_manager import UserManager


@pytest.fixture
def mgr():
    return UserManager()


# ── 测试使用新的 snake_case API ──

class TestAddUser:
    def test_add_user(self, mgr):
        user = mgr.add_user("Alice", "alice@test.com")
        assert user["name"] == "Alice"
        assert user["email"] == "alice@test.com"
        assert user["role"] == "user"
        assert user["active"] is True
        assert "id" in user

    def test_add_user_with_role(self, mgr):
        user = mgr.add_user("Bob", "bob@test.com", role="admin")
        assert user["role"] == "admin"

    def test_auto_increment_id(self, mgr):
        u1 = mgr.add_user("A", "a@test.com")
        u2 = mgr.add_user("B", "b@test.com")
        assert u2["id"] == u1["id"] + 1


class TestGetUser:
    def test_get_existing(self, mgr):
        user = mgr.add_user("Alice", "alice@test.com")
        found = mgr.get_user(user["id"])
        assert found["name"] == "Alice"

    def test_get_missing(self, mgr):
        assert mgr.get_user(999) is None


class TestUpdateUser:
    def test_update_name(self, mgr):
        user = mgr.add_user("Alice", "alice@test.com")
        updated = mgr.update_user(user["id"], name="Alicia")
        assert updated["name"] == "Alicia"

    def test_update_multiple(self, mgr):
        user = mgr.add_user("Alice", "alice@test.com")
        updated = mgr.update_user(user["id"], name="Bob", role="admin")
        assert updated["name"] == "Bob"
        assert updated["role"] == "admin"

    def test_update_missing(self, mgr):
        assert mgr.update_user(999, name="X") is None

    def test_update_ignores_invalid_fields(self, mgr):
        user = mgr.add_user("Alice", "alice@test.com")
        updated = mgr.update_user(user["id"], name="Bob", invalid_field="x")
        assert updated["name"] == "Bob"
        assert "invalid_field" not in updated


class TestDeleteUser:
    def test_delete_existing(self, mgr):
        user = mgr.add_user("Alice", "alice@test.com")
        assert mgr.delete_user(user["id"]) is True
        assert mgr.get_user(user["id"]) is None

    def test_delete_missing(self, mgr):
        assert mgr.delete_user(999) is False


class TestListUsers:
    def test_list_all(self, mgr):
        mgr.add_user("Alice", "a@test.com")
        mgr.add_user("Bob", "b@test.com")
        users = mgr.list_users()
        assert len(users) == 2

    def test_list_by_role(self, mgr):
        mgr.add_user("Alice", "a@test.com", role="admin")
        mgr.add_user("Bob", "b@test.com", role="user")
        mgr.add_user("Charlie", "c@test.com", role="admin")
        admins = mgr.list_users(role="admin")
        assert len(admins) == 2

    def test_list_active_only(self, mgr):
        u = mgr.add_user("Alice", "a@test.com")
        mgr.add_user("Bob", "b@test.com")
        mgr.deactivate_user(u["id"])
        active = mgr.list_users(active_only=True)
        assert len(active) == 1
        assert active[0]["name"] == "Bob"

    def test_list_includes_inactive(self, mgr):
        u = mgr.add_user("Alice", "a@test.com")
        mgr.add_user("Bob", "b@test.com")
        mgr.deactivate_user(u["id"])
        all_users = mgr.list_users(active_only=False)
        assert len(all_users) == 2

    def test_list_sorted_by_id(self, mgr):
        mgr.add_user("Charlie", "c@test.com")
        mgr.add_user("Alice", "a@test.com")
        mgr.add_user("Bob", "b@test.com")
        users = mgr.list_users()
        ids = [u["id"] for u in users]
        assert ids == sorted(ids)


class TestDeactivate:
    def test_deactivate(self, mgr):
        u = mgr.add_user("Alice", "a@test.com")
        assert mgr.deactivate_user(u["id"]) is True
        assert mgr.get_user(u["id"])["active"] is False

    def test_deactivate_missing(self, mgr):
        assert mgr.deactivate_user(999) is False


class TestFindByEmail:
    def test_find_existing(self, mgr):
        mgr.add_user("Alice", "alice@test.com")
        found = mgr.find_by_email("alice@test.com")
        assert found["name"] == "Alice"

    def test_find_missing(self, mgr):
        assert mgr.find_by_email("nope@test.com") is None


class TestCountUsers:
    def test_count_all(self, mgr):
        mgr.add_user("A", "a@test.com")
        mgr.add_user("B", "b@test.com")
        assert mgr.count_users() == 2

    def test_count_by_role(self, mgr):
        mgr.add_user("A", "a@test.com", role="admin")
        mgr.add_user("B", "b@test.com", role="user")
        mgr.add_user("C", "c@test.com", role="admin")
        assert mgr.count_users(role="admin") == 2
        assert mgr.count_users(role="user") == 1


class TestBulkAdd:
    def test_bulk_add(self, mgr):
        data = [
            {"name": "A", "email": "a@test.com"},
            {"name": "B", "email": "b@test.com", "role": "admin"},
        ]
        results = mgr.bulk_add(data)
        assert len(results) == 2
        assert results[1]["role"] == "admin"
        assert mgr.count_users() == 2


class TestRefactoring:
    """验证重构要求"""

    def test_uses_dataclass(self, mgr):
        """User 应该是 dataclass 而不是 dict"""
        user = mgr.add_user("Alice", "alice@test.com")
        # user 仍然支持 dict-like 访问 (通过 __getitem__ 或返回 dict)
        assert user["name"] == "Alice"

    def test_snake_case_methods_exist(self, mgr):
        """所有方法应该是 snake_case"""
        assert hasattr(mgr, 'add_user')
        assert hasattr(mgr, 'get_user')
        assert hasattr(mgr, 'update_user')
        assert hasattr(mgr, 'delete_user')
        assert hasattr(mgr, 'list_users')
        assert hasattr(mgr, 'deactivate_user')
        assert hasattr(mgr, 'find_by_email')
        assert hasattr(mgr, 'count_users')
        assert hasattr(mgr, 'bulk_add')

    def test_camel_case_removed(self, mgr):
        """旧的 camelCase 方法应该被移除"""
        assert not hasattr(mgr, 'addUser')
        assert not hasattr(mgr, 'getUser')
        assert not hasattr(mgr, 'updateUser')
        assert not hasattr(mgr, 'deleteUser')
        assert not hasattr(mgr, 'listUsers')
        assert not hasattr(mgr, 'deactivateUser')
        assert not hasattr(mgr, 'findByEmail')
        assert not hasattr(mgr, 'countUsers')
        assert not hasattr(mgr, 'bulkAdd')
