# 用户管理系统 — 接口命名混乱，需要重构
# 任务：将所有方法名改为一致的命名风格（snake_case），
# 同时将 user dict 改为 User dataclass，但所有测试必须通过
# 注意：不能改测试文件

class UserManager:
    def __init__(self):
        self._users = {}  # id -> user dict
        self._next_id = 1

    def addUser(self, name: str, email: str, role: str = "user") -> dict:
        """添加用户，返回用户 dict"""
        uid = self._next_id
        self._next_id += 1
        user = {"id": uid, "name": name, "email": email, "role": role, "active": True}
        self._users[uid] = user
        return user

    def getUser(self, user_id: int) -> dict | None:
        return self._users.get(user_id)

    def updateUser(self, user_id: int, **fields) -> dict | None:
        """更新用户字段，返回更新后的用户"""
        user = self._users.get(user_id)
        if not user:
            return None
        for k, v in fields.items():
            if k in ("name", "email", "role", "active"):
                user[k] = v
        return user

    def deleteUser(self, user_id: int) -> bool:
        if user_id in self._users:
            del self._users[user_id]
            return True
        return False

    def listUsers(self, role: str = None, active_only: bool = True) -> list[dict]:
        """列出用户，支持按 role 过滤"""
        result = []
        for u in self._users.values():
            if active_only and not u["active"]:
                continue
            if role and u["role"] != role:
                continue
            result.append(u)
        return sorted(result, key=lambda x: x["id"])

    def deactivateUser(self, user_id: int) -> bool:
        user = self._users.get(user_id)
        if user:
            user["active"] = False
            return True
        return False

    def findByEmail(self, email: str) -> dict | None:
        for u in self._users.values():
            if u["email"] == email:
                return u
        return None

    def countUsers(self, role: str = None) -> int:
        if role:
            return sum(1 for u in self._users.values() if u["role"] == role)
        return len(self._users)

    def bulkAdd(self, users_data: list[dict]) -> list[dict]:
        """批量添加用户"""
        results = []
        for data in users_data:
            user = self.addUser(
                name=data["name"],
                email=data["email"],
                role=data.get("role", "user")
            )
            results.append(user)
        return results
