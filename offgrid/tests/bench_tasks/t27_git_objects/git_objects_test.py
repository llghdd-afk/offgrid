"""Tests for git object model implementation.

DO NOT MODIFY THIS FILE. Fix the bugs in objects.py, refs.py, and index.py.
"""

import hashlib
import pytest

from objects import Blob, Tree, TreeEntry, Commit, ObjectStore, GitObject
from refs import Ref, RefStore, find_merge_base
from index import Index, IndexEntry


# ============================================================
# Blob tests
# ============================================================

class TestBlob:
    def test_blob_stores_content(self):
        blob = Blob(b"hello world")
        assert blob.data == b"hello world"
        assert blob.obj_type == "blob"

    def test_blob_sha_matches_git_format(self):
        """Git computes SHA as: SHA1('blob <len>\\0<content>')
        The \\0 is a null byte, not a space.
        """
        data = b"hello world"
        blob = Blob(data)
        # Manually compute the correct SHA
        expected = hashlib.sha1(b"blob 11\0hello world").hexdigest()
        assert blob.sha == expected, (
            f"Blob SHA should use null byte separator. "
            f"Expected {expected}, got {blob.sha}"
        )

    def test_blob_sha_known_value(self):
        """Verify against a known git blob SHA."""
        blob = Blob(b"hello world")
        # This is the actual SHA that `echo -n 'hello world' | git hash-object --stdin` produces
        assert blob.sha == "95d09f2b10159347eece71399a7e2e907ea3df4f"

    def test_empty_blob_sha(self):
        blob = Blob(b"")
        expected = hashlib.sha1(b"blob 0\0").hexdigest()
        assert blob.sha == expected

    def test_blob_repr(self):
        blob = Blob(b"test")
        assert blob.sha[:8] in repr(blob)


# ============================================================
# Tree tests
# ============================================================

class TestTree:
    def test_tree_entry_sorting_directories_vs_files(self):
        """Git sorts tree entries so that directories sort as if
        their name has '/' appended. This means:
          - 'foo' (dir, mode 40000) sorts AFTER 'foo.txt' (file)
          - 'foo' (dir) sorts AFTER 'foo-bar' (file)
          - 'bar' (dir) sorts BEFORE 'car' (file)
        because 'foo/' > 'foo.txt' and 'foo/' > 'foo-bar' in byte order.
        """
        entries = [
            TreeEntry("40000", "foo", "a" * 40),      # directory
            TreeEntry("100644", "foo.txt", "b" * 40),  # file
            TreeEntry("100644", "foo-bar", "c" * 40),  # file
        ]
        tree = Tree(entries)
        names = [e.name for e in tree.entries]
        # 'foo-bar' < 'foo.txt' < 'foo/' in byte order
        # '-' (0x2D) < '.' (0x2E) < '/' (0x2F)
        assert names == ["foo-bar", "foo.txt", "foo"], (
            f"Directory 'foo' should sort after 'foo.txt' and 'foo-bar' "
            f"because Git appends '/' for directory sort comparison. Got: {names}"
        )

    def test_tree_sorting_simple(self):
        """Simple case: directories and files with distinct prefixes."""
        entries = [
            TreeEntry("100644", "zebra.txt", "a" * 40),
            TreeEntry("40000", "alpha", "b" * 40),
            TreeEntry("100644", "beta.py", "c" * 40),
        ]
        tree = Tree(entries)
        names = [e.name for e in tree.entries]
        # alpha/ (dir) -> compare as 'alpha/'
        # beta.py -> compare as 'beta.py'
        # zebra.txt -> compare as 'zebra.txt'
        assert names == ["alpha", "beta.py", "zebra.txt"]

    def test_tree_sorting_tricky_suffix(self):
        """Edge case: 'ab' as dir vs 'ab.c' as file.
        'ab/' > 'ab.c' because '/' (0x2F) > '.' (0x2E)
        """
        entries = [
            TreeEntry("40000", "ab", "a" * 40),
            TreeEntry("100644", "ab.c", "b" * 40),
        ]
        tree = Tree(entries)
        names = [e.name for e in tree.entries]
        assert names == ["ab.c", "ab"], (
            f"Dir 'ab' should sort after 'ab.c'. Got: {names}"
        )

    def test_tree_content_uses_raw_sha(self):
        """Tree entries must store the 20-byte raw SHA, not 40-char hex string."""
        sha_hex = "95d09f2b10159347eece71399a7e2e907ea3df4f"
        entry = TreeEntry("100644", "hello.txt", sha_hex)
        tree = Tree([entry])

        # Manually build expected content
        expected_content = b"100644 hello.txt\0" + bytes.fromhex(sha_hex)
        assert tree.content == expected_content, (
            f"Tree content should use 20-byte raw SHA (length {len(expected_content)}), "
            f"but got content of length {len(tree.content)}. "
            f"The SHA should be raw bytes, not hex string."
        )

    def test_tree_sha_correct(self):
        """Verify tree SHA is computed correctly (depends on both
        correct content format AND correct header format).
        """
        sha_hex = "95d09f2b10159347eece71399a7e2e907ea3df4f"
        entry = TreeEntry("100644", "hello.txt", sha_hex)
        tree = Tree([entry])

        expected_content = b"100644 hello.txt\0" + bytes.fromhex(sha_hex)
        expected_header = f"tree {len(expected_content)}\0".encode()
        expected_sha = hashlib.sha1(expected_header + expected_content).hexdigest()
        assert tree.sha == expected_sha

    def test_tree_add_entry(self):
        tree = Tree()
        tree.add_entry(TreeEntry("100644", "file.txt", "a" * 40))
        assert len(tree.entries) == 1
        assert tree.entries[0].name == "file.txt"


# ============================================================
# Commit tests
# ============================================================

class TestCommit:
    def test_commit_type(self):
        c = Commit(tree_sha="a" * 40, message="initial")
        assert c.obj_type == "commit"

    def test_commit_sha_uses_null_byte(self):
        """Commit SHA should also use null byte in header."""
        c = Commit(tree_sha="a" * 40, message="test")
        content = c.content
        expected_header = f"commit {len(content)}\0".encode()
        expected_sha = hashlib.sha1(expected_header + content).hexdigest()
        assert c.sha == expected_sha

    def test_commit_content_format(self):
        c = Commit(
            tree_sha="abc123" + "0" * 34,
            parent_shas=["def456" + "0" * 34],
            author="Alice <alice@test.com>",
            message="Add feature",
        )
        content = c.content.decode()
        assert content.startswith("tree abc123")
        assert "parent def456" in content
        assert "author Alice <alice@test.com>" in content
        assert content.endswith("Add feature")

    def test_commit_no_parents(self):
        c = Commit(tree_sha="a" * 40, message="root")
        content = c.content.decode()
        assert "parent" not in content

    def test_commit_multiple_parents(self):
        c = Commit(
            tree_sha="a" * 40,
            parent_shas=["b" * 40, "c" * 40],
            message="merge",
        )
        content = c.content.decode()
        assert content.count("parent") == 2


# ============================================================
# ObjectStore tests
# ============================================================

class TestObjectStore:
    def test_save_and_load(self):
        store = ObjectStore()
        blob = Blob(b"data")
        sha = store.save(blob)
        loaded = store.load(sha)
        assert loaded is blob

    def test_load_missing(self):
        store = ObjectStore()
        assert store.load("nonexistent") is None

    def test_contains(self):
        store = ObjectStore()
        blob = Blob(b"x")
        sha = store.save(blob)
        assert store.contains(sha)
        assert not store.contains("other")

    def test_all_objects(self):
        store = ObjectStore()
        b1 = Blob(b"a")
        b2 = Blob(b"b")
        store.save(b1)
        store.save(b2)
        assert len(store.all_objects()) == 2


# ============================================================
# Ref tests
# ============================================================

class TestRefStore:
    def test_create_and_get(self):
        rs = RefStore()
        ref = rs.create("refs/heads/main", "abc123")
        assert ref.name == "refs/heads/main"
        assert ref.target == "abc123"
        assert rs.get("refs/heads/main") is ref

    def test_update(self):
        rs = RefStore()
        rs.create("refs/heads/main", "old_sha")
        rs.update("refs/heads/main", "new_sha")
        assert rs.get("refs/heads/main").target == "new_sha"

    def test_delete(self):
        rs = RefStore()
        rs.create("refs/heads/main", "abc")
        assert rs.delete("refs/heads/main")
        assert rs.get("refs/heads/main") is None

    def test_resolve_direct_ref(self):
        rs = RefStore()
        rs.create("refs/heads/main", "sha_abc")
        assert rs.resolve_ref("refs/heads/main") == "sha_abc"

    def test_resolve_symbolic_ref(self):
        rs = RefStore()
        rs.create("refs/heads/main", "sha_abc")
        rs.create("HEAD", "ref: refs/heads/main")
        assert rs.resolve_ref("HEAD") == "sha_abc"

    def test_resolve_chained_symbolic_refs(self):
        rs = RefStore()
        rs.create("refs/heads/main", "sha_final")
        rs.create("refs/heads/alias", "ref: refs/heads/main")
        rs.create("HEAD", "ref: refs/heads/alias")
        assert rs.resolve_ref("HEAD") == "sha_final"

    def test_resolve_missing_ref(self):
        rs = RefStore()
        assert rs.resolve_ref("nonexistent") is None

    def test_resolve_symbolic_ref_cycle_detection(self):
        """Circular symbolic refs must not cause infinite recursion."""
        rs = RefStore()
        rs.create("refs/heads/a", "ref: refs/heads/b")
        rs.create("refs/heads/b", "ref: refs/heads/a")
        # Should return None (or raise a controlled error), NOT infinite recurse
        result = rs.resolve_ref("refs/heads/a")
        assert result is None, (
            "Circular symbolic refs should return None, not infinite loop"
        )

    def test_resolve_self_referencing_symbolic_ref(self):
        """A ref pointing to itself should not infinite loop."""
        rs = RefStore()
        rs.create("HEAD", "ref: HEAD")
        result = rs.resolve_ref("HEAD")
        assert result is None

    def test_resolve_three_way_cycle(self):
        """A -> B -> C -> A cycle detection."""
        rs = RefStore()
        rs.create("refs/a", "ref: refs/b")
        rs.create("refs/b", "ref: refs/c")
        rs.create("refs/c", "ref: refs/a")
        result = rs.resolve_ref("refs/a")
        assert result is None

    def test_list_refs(self):
        rs = RefStore()
        rs.create("refs/heads/main", "sha1")
        rs.create("refs/heads/dev", "sha2")
        assert len(rs.list_refs()) == 2


# ============================================================
# Merge-base tests
# ============================================================

class TestMergeBase:
    def test_simple_linear_history(self):
        """A -> B -> C, merge-base(A, C) = C (C is ancestor of both... no)
        Actually: C -> B -> A (C's parent is B, B's parent is A)
        merge-base(C, B) = B
        """
        parents = {
            "C": ["B"],
            "B": ["A"],
            "A": [],
        }
        assert find_merge_base(parents, "C", "B") == "B"
        assert find_merge_base(parents, "C", "A") == "A"
        assert find_merge_base(parents, "B", "A") == "A"

    def test_fork_and_merge(self):
        """
            A
           / \\
          B   C
           \\ /
            D (merge commit)

        parents: D -> [B, C], B -> [A], C -> [A]
        merge-base(B, C) = A
        merge-base(D, A) = A
        """
        parents = {
            "D": ["B", "C"],
            "B": ["A"],
            "C": ["A"],
            "A": [],
        }
        assert find_merge_base(parents, "B", "C") == "A"
        assert find_merge_base(parents, "D", "A") == "A"

    def test_diamond_merge_base(self):
        """
        Diamond graph:
            R
           / \\
          X   Y
         / \\ |
        P   Q|
         \\ / |
          M  |
           \\ |
            N (merge M and Y)

        parents: N -> [M, Y], M -> [P, Q], P -> [X], Q -> [X], X -> [R], Y -> [R]
        merge-base(M, Y) should be R (the root, common ancestor via X->R and Y->R)
        """
        parents = {
            "N": ["M", "Y"],
            "M": ["P", "Q"],
            "P": ["X"],
            "Q": ["X"],
            "X": ["R"],
            "Y": ["R"],
            "R": [],
        }
        assert find_merge_base(parents, "M", "Y") == "R"

    def test_merge_base_same_commit(self):
        parents = {"A": []}
        assert find_merge_base(parents, "A", "A") == "A"

    def test_merge_base_unrelated(self):
        parents = {
            "A": [],
            "B": [],
        }
        assert find_merge_base(parents, "A", "B") is None

    def test_merge_base_finds_closest_ancestor(self):
        """
        Graph:
          A -> B -> C -> D
                \\-> E -> F

        merge-base(D, F) should be B (not A)
        """
        parents = {
            "D": ["C"],
            "C": ["B"],
            "B": ["A"],
            "F": ["E"],
            "E": ["B"],
            "A": [],
        }
        result = find_merge_base(parents, "D", "F")
        assert result == "B", f"Expected merge-base B, got {result}"

    def test_merge_base_with_shortcut_edge(self):
        """
        Graph where a commit has both a near and far ancestor as parents:

            A
            |
            B
            |
            C
           / \\
          |   D (D's parent is C)
          |
          (shortcut)

        E's parents are [D, A] — D is close common ancestor, A is far.
        ancestors of C = {C, B, A}
        merge-base(C, E) must be C (not A).

        A BFS from E checks D first (closer), then A. D is not in ancestors of C
        directly (D descends from C). But we need a graph where BFS vs DFS
        actually differs.

        Correct graph:
            A
            |
            B
            |
            C
            |
            D  (parents: [C, A])  — D has shortcut edge to A

        merge-base(C, D):
        ancestors of C = {C, B, A}
        BFS from D: check D (not in ancestors), enqueue parents [C, A]
          -> pop C first (BFS), C IS in ancestors -> return C (correct!)
        DFS from D: check D (not in ancestors), push parents [C, A]
          -> pop A first (DFS/LIFO), A IS in ancestors -> return A (WRONG!)
        """
        parents = {
            "D": ["C", "A"],
            "C": ["B"],
            "B": ["A"],
            "A": [],
        }
        result = find_merge_base(parents, "C", "D")
        assert result == "C", (
            f"merge-base(C, D) should be C (closest common ancestor), got {result}"
        )


# ============================================================
# Index tests
# ============================================================

class TestIndex:
    def test_stage_file(self):
        store = ObjectStore()
        idx = Index(store)
        sha = idx.stage_file("hello.txt", b"hello world")
        assert sha == Blob(b"hello world").sha
        assert idx.get("hello.txt") is not None
        assert idx.get("hello.txt").sha == sha

    def test_list_entries_sorted(self):
        store = ObjectStore()
        idx = Index(store)
        idx.stage_file("c.txt", b"c")
        idx.stage_file("a.txt", b"a")
        idx.stage_file("b.txt", b"b")
        paths = [e.path for e in idx.list_entries()]
        assert paths == ["a.txt", "b.txt", "c.txt"]

    def test_remove_entry(self):
        store = ObjectStore()
        idx = Index(store)
        idx.stage_file("file.txt", b"data")
        assert idx.remove("file.txt")
        assert idx.get("file.txt") is None

    def test_clear(self):
        store = ObjectStore()
        idx = Index(store)
        idx.stage_file("a.txt", b"a")
        idx.stage_file("b.txt", b"b")
        idx.clear()
        assert idx.entry_count == 0

    def test_entry_count(self):
        store = ObjectStore()
        idx = Index(store)
        assert idx.entry_count == 0
        idx.stage_file("f.txt", b"f")
        assert idx.entry_count == 1

    def test_overwrite_entry(self):
        store = ObjectStore()
        idx = Index(store)
        sha1 = idx.stage_file("file.txt", b"v1")
        sha2 = idx.stage_file("file.txt", b"v2")
        assert sha1 != sha2
        assert idx.get("file.txt").sha == sha2
        assert idx.entry_count == 1


# ============================================================
# Integration tests
# ============================================================

class TestIntegration:
    def test_full_commit_workflow(self):
        """Stage files, create tree, create commit — full workflow."""
        store = ObjectStore()
        idx = Index(store)

        # Stage files
        sha1 = idx.stage_file("main.py", b"print('hello')")
        sha2 = idx.stage_file("utils.py", b"def helper(): pass")

        # Build tree from index
        entries = [
            TreeEntry("100644", e.path, e.sha)
            for e in idx.list_entries()
        ]
        tree = Tree(entries)
        tree_sha = store.save(tree)

        # Create commit
        commit = Commit(tree_sha=tree_sha, message="Initial commit")
        commit_sha = store.save(commit)

        # Verify everything is in the store
        assert store.contains(sha1)
        assert store.contains(sha2)
        assert store.contains(tree_sha)
        assert store.contains(commit_sha)

        # Verify commit points to correct tree
        loaded_commit = store.load(commit_sha)
        assert loaded_commit.tree_sha == tree_sha

    def test_sha_stability(self):
        """Same content should always produce the same SHA."""
        b1 = Blob(b"deterministic")
        b2 = Blob(b"deterministic")
        assert b1.sha == b2.sha

        t1 = Tree([TreeEntry("100644", "f.txt", b1.sha)])
        t2 = Tree([TreeEntry("100644", "f.txt", b2.sha)])
        assert t1.sha == t2.sha
