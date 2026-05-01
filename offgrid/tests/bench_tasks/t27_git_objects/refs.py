"""Git reference management: refs, symbolic refs, and merge-base."""

from collections import deque


class Ref:
    """A git reference pointing to a SHA or another ref."""

    def __init__(self, name: str, target: str):
        self.name = name
        self.target = target

    @property
    def is_symbolic(self) -> bool:
        return self.target.startswith("ref: ")

    @property
    def symbolic_target(self) -> str | None:
        if self.is_symbolic:
            return self.target[5:]  # strip "ref: "
        return None

    def __repr__(self):
        return f"Ref({self.name!r}, {self.target!r})"


class RefStore:
    """Store and manage git references."""

    def __init__(self):
        self._refs: dict[str, Ref] = {}

    def create(self, name: str, target: str) -> Ref:
        ref = Ref(name, target)
        self._refs[name] = ref
        return ref

    def get(self, name: str) -> Ref | None:
        return self._refs.get(name)

    def update(self, name: str, target: str) -> Ref | None:
        if name in self._refs:
            self._refs[name].target = target
            return self._refs[name]
        return None

    def delete(self, name: str) -> bool:
        if name in self._refs:
            del self._refs[name]
            return True
        return False

    def list_refs(self) -> list[Ref]:
        return list(self._refs.values())

    def resolve_ref(self, name: str) -> str | None:
        """Resolve a ref name to a final SHA, following symbolic refs.

        Returns None if the ref doesn't exist.
        """
        ref = self._refs.get(name)
        if ref is None:
            return None
        if ref.is_symbolic:
            return self.resolve_ref(ref.symbolic_target)
        return ref.target


def find_merge_base(commit_parents: dict[str, list[str]],
                    sha1: str, sha2: str) -> str | None:
    """Find the merge-base (lowest common ancestor) of two commits.

    commit_parents: dict mapping commit SHA -> list of parent SHAs
    Returns the SHA of the LCA, or None if unrelated.
    """
    # Collect all ancestors of sha1
    ancestors1 = set()
    queue = [sha1]
    while queue:
        current = queue.pop(0)
        if current in ancestors1:
            continue
        ancestors1.add(current)
        for parent in commit_parents.get(current, []):
            queue.append(parent)

    # Search from sha2, first hit in ancestors1 is the merge-base
    queue2 = [sha2]
    visited = set()
    while queue2:
        current = queue2.pop()
        if current in visited:
            continue
        visited.add(current)
        if current in ancestors1:
            return current
        for parent in commit_parents.get(current, []):
            queue2.append(parent)

    return None
