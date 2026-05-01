# 基于角色的访问控制 (RBAC) 系统
#
# 这个系统有两个已知 bug 需要修复，同时需要重构拆分：
# 1. 运行测试找出代码中的问题并修复
# 2. 将代码拆分为 roles.py、permissions.py、rbac.py 三个模块
# 3. rbac_system.py 作为主模块 re-export 所有公开类
# 4. 所有测试必须通过，不要修改测试文件

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional


@dataclass(frozen=True)
class Permission:
    """权限: 资源 + 操作。action='*' 表示通配符。"""
    resource: str
    action: str
    description: str = ""

    def __str__(self):
        return f"{self.resource}:{self.action}"

    @classmethod
    def from_string(cls, perm_str: str, description: str = "") -> "Permission":
        parts = perm_str.split(":", 1)
        if len(parts) != 2:
            raise ValueError(f"Invalid permission format: {perm_str!r}, expected 'resource:action'")
        return cls(resource=parts[0], action=parts[1], description=description)

    def matches(self, resource: str, action: str) -> bool:
        """检查权限是否匹配(支持通配符 action='*')"""
        if self.resource == resource and self.action == action:
            return True
        return False


class Role:
    """角色: 包含权限集合，支持父角色继承。"""

    def __init__(self, name: str, description: str = ""):
        self.name = name
        self.description = description
        self._permissions: set[Permission] = set()
        self._parents: list[Role] = []

    @property
    def permissions(self) -> frozenset[Permission]:
        return frozenset(self._permissions)

    @property
    def parents(self) -> tuple[Role, ...]:
        return tuple(self._parents)

    def add_permission(self, permission: Permission) -> None:
        self._permissions.add(permission)

    def remove_permission(self, permission: Permission) -> None:
        self._permissions.discard(permission)

    def add_parent(self, parent: "Role") -> None:
        if parent.name == self.name:
            raise ValueError("A role cannot inherit from itself")
        if parent in self._parents:
            return
        if self._is_ancestor_of(parent):
            raise ValueError(f"Adding {parent.name} as parent of {self.name} would create a cycle")
        self._parents.append(parent)

    def _is_ancestor_of(self, other: "Role") -> bool:
        """检查 self 是否是 other 的祖先"""
        visited = set()
        stack = [other]
        while stack:
            current = stack.pop()
            if current.name in visited:
                continue
            visited.add(current.name)
            for p in current._parents:
                if p.name == self.name:
                    return True
                stack.append(p)
        return False

    def has_permission(self, resource: str, action: str) -> bool:
        """检查角色是否拥有权限(含继承)"""
        for perm in self._permissions:
            if perm.matches(resource, action):
                return True
        # 检查继承的权限
        for parent in self._parents:
            for perm in parent._permissions:
                if perm.matches(resource, action):
                    return True
        return False

    def get_all_permissions(self) -> set[Permission]:
        """获取所有权限(含继承)"""
        all_perms = set(self._permissions)
        for parent in self._parents:
            all_perms.update(parent._permissions)
        return all_perms

    def __repr__(self):
        return f"Role({self.name!r})"

    def __eq__(self, other):
        if not isinstance(other, Role):
            return NotImplemented
        return self.name == other.name

    def __hash__(self):
        return hash(self.name)


class RBACManager:
    """RBAC 管理器: 角色管理、用户绑定、权限检查。"""

    def __init__(self):
        self._roles: dict[str, Role] = {}
        self._user_roles: dict[str, set[str]] = {}

    def create_role(self, name: str, description: str = "") -> Role:
        if name in self._roles:
            raise ValueError(f"Role {name!r} already exists")
        role = Role(name, description)
        self._roles[name] = role
        return role

    def get_role(self, name: str) -> Optional[Role]:
        return self._roles.get(name)

    def delete_role(self, name: str) -> bool:
        if name not in self._roles:
            return False
        del self._roles[name]
        for user_roles in self._user_roles.values():
            user_roles.discard(name)
        return True

    def list_roles(self) -> list[str]:
        return sorted(self._roles.keys())

    def assign_role(self, user_id: str, role_name: str) -> None:
        if role_name not in self._roles:
            raise ValueError(f"Role {role_name!r} does not exist")
        if user_id not in self._user_roles:
            self._user_roles[user_id] = set()
        self._user_roles[user_id].add(role_name)

    def revoke_role(self, user_id: str, role_name: str) -> None:
        if user_id in self._user_roles:
            self._user_roles[user_id].discard(role_name)

    def get_user_roles(self, user_id: str) -> list[str]:
        return sorted(self._user_roles.get(user_id, set()))

    def get_users_with_role(self, role_name: str) -> list[str]:
        return sorted(uid for uid, roles in self._user_roles.items() if role_name in roles)

    def check_permission(self, user_id: str, resource: str, action: str) -> bool:
        for rn in self._user_roles.get(user_id, set()):
            role = self._roles.get(rn)
            if role and role.has_permission(resource, action):
                return True
        return False

    def get_user_permissions(self, user_id: str) -> set[Permission]:
        all_perms: set[Permission] = set()
        for rn in self._user_roles.get(user_id, set()):
            role = self._roles.get(rn)
            if role:
                all_perms.update(role.get_all_permissions())
        return all_perms

    def setup_hierarchy(self, hierarchy: dict[str, list[str]]) -> None:
        """批量设置继承: {"admin": ["manager"], "manager": ["user"]}"""
        for role_name, parent_names in hierarchy.items():
            role = self._roles.get(role_name)
            if not role:
                raise ValueError(f"Role {role_name!r} does not exist")
            for pn in parent_names:
                parent = self._roles.get(pn)
                if not parent:
                    raise ValueError(f"Parent role {pn!r} does not exist")
                role.add_parent(parent)

    def grant_permissions(self, role_name: str, permissions: list[Permission]) -> None:
        role = self._roles.get(role_name)
        if not role:
            raise ValueError(f"Role {role_name!r} does not exist")
        for perm in permissions:
            role.add_permission(perm)
