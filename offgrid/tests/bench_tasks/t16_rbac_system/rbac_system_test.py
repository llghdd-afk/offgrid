import pytest
import importlib
import os

from rbac_system import Permission, Role, RBACManager


# ── Permission 基础测试 ──

class TestPermission:
    def test_create_permission(self):
        p = Permission("documents", "read")
        assert p.resource == "documents"
        assert p.action == "read"

    def test_permission_str(self):
        p = Permission("documents", "write", description="Write docs")
        assert str(p) == "documents:write"

    def test_from_string(self):
        p = Permission.from_string("users:delete", description="Delete users")
        assert p.resource == "users"
        assert p.action == "delete"
        assert p.description == "Delete users"

    def test_from_string_invalid(self):
        with pytest.raises(ValueError):
            Permission.from_string("invalid_no_colon")

    def test_permission_equality(self):
        p1 = Permission("docs", "read")
        p2 = Permission("docs", "read")
        assert p1 == p2

    def test_permission_hashable(self):
        p1 = Permission("docs", "read")
        p2 = Permission("docs", "read")
        assert len({p1, p2}) == 1

    def test_wildcard_matches_any_action(self):
        """通配符权限 action='*' 应匹配同资源的任意操作"""
        p = Permission("documents", "*")
        assert p.matches("documents", "read") is True
        assert p.matches("documents", "write") is True
        assert p.matches("documents", "delete") is True

    def test_wildcard_does_not_match_different_resource(self):
        p = Permission("documents", "*")
        assert p.matches("users", "read") is False

    def test_exact_match(self):
        p = Permission("documents", "read")
        assert p.matches("documents", "read") is True
        assert p.matches("documents", "write") is False


# ── Role 基础测试 ──

class TestRole:
    def test_create_role(self):
        r = Role("admin")
        assert r.name == "admin"
        assert len(r.permissions) == 0

    def test_add_permission(self):
        r = Role("editor")
        p = Permission("articles", "edit")
        r.add_permission(p)
        assert p in r.permissions

    def test_remove_permission(self):
        r = Role("editor")
        p = Permission("articles", "edit")
        r.add_permission(p)
        r.remove_permission(p)
        assert p not in r.permissions

    def test_role_equality_by_name(self):
        r1 = Role("admin")
        r2 = Role("admin")
        assert r1 == r2

    def test_direct_permission_check(self):
        r = Role("viewer")
        r.add_permission(Permission("reports", "read"))
        assert r.has_permission("reports", "read") is True
        assert r.has_permission("reports", "write") is False

    def test_cannot_inherit_from_self(self):
        r = Role("admin")
        with pytest.raises(ValueError):
            r.add_parent(r)


# ── Role 继承测试（关键 — 触发 BUG 1）──

class TestRoleInheritance:
    def _build_three_level_hierarchy(self):
        """创建三级角色链: admin -> manager -> user"""
        user_role = Role("user")
        user_role.add_permission(Permission("profile", "read"))
        user_role.add_permission(Permission("profile", "edit"))

        manager_role = Role("manager")
        manager_role.add_permission(Permission("reports", "read"))
        manager_role.add_permission(Permission("team", "manage"))
        manager_role.add_parent(user_role)

        admin_role = Role("admin")
        admin_role.add_permission(Permission("system", "configure"))
        admin_role.add_parent(manager_role)

        return user_role, manager_role, admin_role

    def test_direct_parent_permission(self):
        """manager 应该继承 user 的权限"""
        user_role, manager_role, _ = self._build_three_level_hierarchy()
        assert manager_role.has_permission("profile", "read") is True

    def test_grandparent_permission(self):
        """admin 应该继承 user（祖父角色）的权限"""
        user_role, manager_role, admin_role = self._build_three_level_hierarchy()
        # admin -> manager -> user, user 有 profile:read
        assert admin_role.has_permission("profile", "read") is True
        assert admin_role.has_permission("profile", "edit") is True

    def test_grandparent_get_all_permissions(self):
        """get_all_permissions 应包含祖父角色的权限"""
        _, _, admin_role = self._build_three_level_hierarchy()
        all_perms = admin_role.get_all_permissions()
        perm_strs = {str(p) for p in all_perms}
        assert "profile:read" in perm_strs
        assert "profile:edit" in perm_strs
        assert "reports:read" in perm_strs
        assert "system:configure" in perm_strs

    def test_four_level_inheritance(self):
        """四级继承链也应正常工作"""
        base = Role("base")
        base.add_permission(Permission("base_resource", "access"))

        level1 = Role("level1")
        level1.add_parent(base)

        level2 = Role("level2")
        level2.add_parent(level1)

        level3 = Role("level3")
        level3.add_parent(level2)

        assert level3.has_permission("base_resource", "access") is True

    def test_cycle_detection(self):
        """循环继承应被拒绝"""
        r1 = Role("r1")
        r2 = Role("r2")
        r1.add_parent(r2)
        with pytest.raises(ValueError):
            r2.add_parent(r1)


# ── RBACManager 测试 ──

class TestRBACManager:
    def test_create_and_get_role(self):
        mgr = RBACManager()
        role = mgr.create_role("admin", "Administrator")
        assert mgr.get_role("admin") is role

    def test_duplicate_role(self):
        mgr = RBACManager()
        mgr.create_role("admin")
        with pytest.raises(ValueError):
            mgr.create_role("admin")

    def test_delete_role(self):
        mgr = RBACManager()
        mgr.create_role("temp")
        assert mgr.delete_role("temp") is True
        assert mgr.get_role("temp") is None

    def test_delete_nonexistent_role(self):
        mgr = RBACManager()
        assert mgr.delete_role("ghost") is False

    def test_list_roles(self):
        mgr = RBACManager()
        mgr.create_role("beta")
        mgr.create_role("alpha")
        assert mgr.list_roles() == ["alpha", "beta"]

    def test_assign_and_check_permission(self):
        mgr = RBACManager()
        role = mgr.create_role("editor")
        role.add_permission(Permission("articles", "write"))
        mgr.assign_role("user1", "editor")
        assert mgr.check_permission("user1", "articles", "write") is True
        assert mgr.check_permission("user1", "articles", "delete") is False

    def test_assign_nonexistent_role(self):
        mgr = RBACManager()
        with pytest.raises(ValueError):
            mgr.assign_role("user1", "ghost")

    def test_revoke_role(self):
        mgr = RBACManager()
        mgr.create_role("viewer")
        mgr.assign_role("u1", "viewer")
        mgr.revoke_role("u1", "viewer")
        assert mgr.get_user_roles("u1") == []

    def test_get_users_with_role(self):
        mgr = RBACManager()
        mgr.create_role("editor")
        mgr.assign_role("alice", "editor")
        mgr.assign_role("bob", "editor")
        assert mgr.get_users_with_role("editor") == ["alice", "bob"]

    def test_user_permission_via_deep_inheritance(self):
        """通过 RBACManager 测试深层继承权限检查"""
        mgr = RBACManager()
        user_role = mgr.create_role("user")
        mgr.create_role("manager")
        mgr.create_role("admin")

        user_role.add_permission(Permission("dashboard", "view"))

        mgr.setup_hierarchy({
            "admin": ["manager"],
            "manager": ["user"],
        })
        mgr.assign_role("alice", "admin")

        # alice 是 admin -> manager -> user, user 有 dashboard:view
        assert mgr.check_permission("alice", "dashboard", "view") is True

    def test_wildcard_permission_via_manager(self):
        """通过 RBACManager 测试通配符权限"""
        mgr = RBACManager()
        superadmin = mgr.create_role("superadmin")
        superadmin.add_permission(Permission("documents", "*"))
        mgr.assign_role("root", "superadmin")

        assert mgr.check_permission("root", "documents", "read") is True
        assert mgr.check_permission("root", "documents", "write") is True
        assert mgr.check_permission("root", "documents", "delete") is True
        assert mgr.check_permission("root", "users", "read") is False

    def test_get_user_permissions_merged(self):
        mgr = RBACManager()
        r1 = mgr.create_role("r1")
        r2 = mgr.create_role("r2")
        r1.add_permission(Permission("a", "read"))
        r2.add_permission(Permission("b", "write"))
        mgr.assign_role("u1", "r1")
        mgr.assign_role("u1", "r2")
        perms = mgr.get_user_permissions("u1")
        perm_strs = {str(p) for p in perms}
        assert "a:read" in perm_strs
        assert "b:write" in perm_strs

    def test_grant_permissions_batch(self):
        mgr = RBACManager()
        role = mgr.create_role("batch_role")
        perms = [Permission("x", "read"), Permission("y", "write")]
        mgr.grant_permissions("batch_role", perms)
        assert role.has_permission("x", "read") is True
        assert role.has_permission("y", "write") is True

    def test_setup_hierarchy_missing_role(self):
        mgr = RBACManager()
        mgr.create_role("admin")
        with pytest.raises(ValueError):
            mgr.setup_hierarchy({"admin": ["nonexistent"]})

    def test_delete_role_removes_from_users(self):
        mgr = RBACManager()
        mgr.create_role("temp")
        mgr.assign_role("u1", "temp")
        mgr.delete_role("temp")
        assert mgr.get_user_roles("u1") == []


# ── 结构测试：拆分为三个模块 ──

class TestModuleStructure:
    """验证代码已被正确拆分为 roles.py, permissions.py, rbac.py"""

    def _get_task_dir(self):
        return os.path.dirname(os.path.abspath(__file__))

    def test_permissions_module_exists(self):
        task_dir = self._get_task_dir()
        assert os.path.isfile(os.path.join(task_dir, "permissions.py")), \
            "permissions.py should exist"

    def test_roles_module_exists(self):
        task_dir = self._get_task_dir()
        assert os.path.isfile(os.path.join(task_dir, "roles.py")), \
            "roles.py should exist"

    def test_rbac_module_exists(self):
        task_dir = self._get_task_dir()
        assert os.path.isfile(os.path.join(task_dir, "rbac.py")), \
            "rbac.py should exist"

    def test_rbac_system_reexports_permission(self):
        """rbac_system.py 应该 re-export Permission"""
        mod = importlib.import_module("rbac_system")
        assert hasattr(mod, "Permission")
        assert mod.Permission is Permission

    def test_rbac_system_reexports_role(self):
        """rbac_system.py 应该 re-export Role"""
        mod = importlib.import_module("rbac_system")
        assert hasattr(mod, "Role")
        assert mod.Role is Role

    def test_rbac_system_reexports_rbacmanager(self):
        """rbac_system.py 应该 re-export RBACManager"""
        mod = importlib.import_module("rbac_system")
        assert hasattr(mod, "RBACManager")
        assert mod.RBACManager is RBACManager

    def test_import_from_permissions_module(self):
        """Permission 应该可以从 permissions 模块直接导入"""
        from permissions import Permission as P
        assert P is Permission

    def test_import_from_roles_module(self):
        """Role 应该可以从 roles 模块直接导入"""
        from roles import Role as R
        assert R is Role

    def test_import_from_rbac_module(self):
        """RBACManager 应该可以从 rbac 模块直接导入"""
        from rbac import RBACManager as M
        assert M is RBACManager
