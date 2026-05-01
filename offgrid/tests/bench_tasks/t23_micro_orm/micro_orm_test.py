"""Tests for micro ORM system.

Tests cover:
- Connection management
- Model CRUD operations
- Field types and table creation
- Foreign key relationships and migration
- Chain query builder
- Aggregate and group_by
- select_related (eager loading)

DO NOT modify this file.
"""

import pytest
import sqlite3
from connection import Database
from model import (
    Model, Field, IntField, StringField, FloatField, BoolField,
    ForeignKey, _model_registry, ModelMeta,
)
from query import QuerySet


# ── Helpers: clear registry between tests ──

@pytest.fixture(autouse=True)
def clean_registry():
    """Clear model registry and DB binding before each test."""
    _model_registry.clear()
    Model._db = None
    yield
    _model_registry.clear()
    Model._db = None


def make_db():
    """Create an in-memory database and connect."""
    db = Database(":memory:")
    db.connect()
    return db


# ══════════════════════════════════════════
# 1. Connection Management
# ══════════════════════════════════════════

class TestConnection:
    def test_connect_and_close(self):
        db = make_db()
        assert db.connected is True
        db.close()
        assert db.connected is False

    def test_context_manager(self):
        with Database(":memory:") as db:
            db.execute("CREATE TABLE t (id INTEGER PRIMARY KEY)")
            db.execute("INSERT INTO t VALUES (1)")
            rows = db.fetchall("SELECT * FROM t")
            assert len(rows) == 1
        assert db.connected is False

    def test_transaction_rollback(self):
        db = make_db()
        db.execute("CREATE TABLE t (id INTEGER PRIMARY KEY, val TEXT)")
        db.commit()

        db.begin()
        db.execute("INSERT INTO t VALUES (1, 'a')")
        db.rollback()

        rows = db.fetchall("SELECT * FROM t")
        assert len(rows) == 0
        db.close()

    def test_fetchone(self):
        db = make_db()
        db.execute("CREATE TABLE t (id INTEGER PRIMARY KEY, name TEXT)")
        db.execute("INSERT INTO t VALUES (1, 'Alice')")
        db.commit()
        row = db.fetchone("SELECT * FROM t WHERE id = ?", [1])
        assert row["name"] == "Alice"
        db.close()


# ══════════════════════════════════════════
# 2. Field Types
# ══════════════════════════════════════════

class TestFieldTypes:
    def test_int_field_type(self):
        f = IntField()
        assert f.sql_type() == "INTEGER"

    def test_string_field_type(self):
        f = StringField()
        assert f.sql_type() == "TEXT"

    def test_bool_field_type(self):
        f = BoolField()
        assert f.sql_type() == "INTEGER"

    def test_float_field_sql_type_is_real(self):
        """FloatField must map to REAL, not FLOAT.
        SQLite type affinity rules: REAL is the correct affinity type.
        FLOAT gets NUMERIC affinity, causing storage differences."""
        f = FloatField()
        assert f.sql_type() == "REAL", (
            f"FloatField.sql_type() should return 'REAL' for correct "
            f"SQLite type affinity, got '{f.sql_type()}'"
        )

    def test_float_field_stores_correctly(self):
        """Verify floats are stored with REAL affinity in the schema."""
        db = make_db()

        class Product(Model):
            id = IntField(primary_key=True)
            price = FloatField()

        Model.bind(db)
        Product.create_table()

        # Check the actual column type in the schema
        schema = db.fetchone(
            "SELECT sql FROM sqlite_master WHERE name = ?",
            [Product.table_name()]
        )
        assert "REAL" in schema["sql"], (
            f"Table schema should use REAL for float columns: {schema['sql']}"
        )

        p = Product(price=3.14)
        p.save()
        p.refresh()
        assert abs(p.price - 3.14) < 1e-10
        db.close()


# ══════════════════════════════════════════
# 3. Model CRUD
# ══════════════════════════════════════════

class TestModelCRUD:
    def test_create_and_read(self):
        db = make_db()

        class User(Model):
            id = IntField(primary_key=True)
            name = StringField()
            age = IntField()

        Model.bind(db)
        User.create_table()

        u = User(name="Alice", age=30)
        u.save()
        assert u.id is not None

        row = db.fetchone("SELECT * FROM users WHERE id = ?", [u.id])
        assert row["name"] == "Alice"
        assert row["age"] == 30
        db.close()

    def test_update(self):
        db = make_db()

        class User(Model):
            id = IntField(primary_key=True)
            name = StringField()

        Model.bind(db)
        User.create_table()

        u = User(name="Alice")
        u.save()
        u.name = "Bob"
        u.save()

        row = db.fetchone("SELECT * FROM users WHERE id = ?", [u.id])
        assert row["name"] == "Bob"
        db.close()

    def test_delete(self):
        db = make_db()

        class User(Model):
            id = IntField(primary_key=True)
            name = StringField()

        Model.bind(db)
        User.create_table()

        u = User(name="Alice")
        u.save()
        uid = u.id
        u.delete()

        row = db.fetchone("SELECT * FROM users WHERE id = ?", [uid])
        assert row is None
        db.close()

    def test_refresh(self):
        db = make_db()

        class User(Model):
            id = IntField(primary_key=True)
            name = StringField()

        Model.bind(db)
        User.create_table()

        u = User(name="Alice")
        u.save()

        # Modify directly in DB
        db.execute("UPDATE users SET name = ? WHERE id = ?", ["Charlie", u.id])
        db.commit()

        u.refresh()
        assert u.name == "Charlie"
        db.close()


# ══════════════════════════════════════════
# 4. Foreign Key - Table Recreate (Migration)
# ══════════════════════════════════════════

class TestForeignKeyMigration:
    def test_recreate_tables_respects_fk_dependency_order(self):
        """When recreating tables (drop + create), tables must be dropped
        in reverse dependency order to avoid FK constraint violations.
        User is defined first, Order references User. If User is dropped
        before Order, FK constraint fails."""
        db = make_db()

        # User defined first (registered first in dict), Order references User
        class User(Model):
            id = IntField(primary_key=True)
            name = StringField()

        class Order(Model):
            id = IntField(primary_key=True)
            user_id = ForeignKey("User")
            total = FloatField()

        Model.bind(db)

        # Initial creation
        Model.create_all_tables()

        # Insert data so FK constraints are active
        u = User(name="Alice")
        u.save()
        o = Order(user_id=u.id, total=99.99)
        o.save()

        # Now recreate: drop all then create again.
        # Dict order is User, Order. Dropping User first while Order
        # still references it should fail — unless properly ordered.
        Model.create_all_tables(recreate=True)

        # Verify tables are empty (recreated)
        users = db.fetchall("SELECT * FROM users")
        orders = db.fetchall("SELECT * FROM orders")
        assert len(users) == 0
        assert len(orders) == 0
        db.close()

    def test_recreate_chain_dependency(self):
        """Chain: A (no FK), B -> A, C -> B.
        Drop must go C, B, A. Create must go A, B, C.
        Defined in order A, B, C so drop in dict order fails."""
        db = make_db()

        class TaskA(Model):
            _table_name = "task_a"
            id = IntField(primary_key=True)
            name = StringField()

        class TaskB(Model):
            _table_name = "task_b"
            id = IntField(primary_key=True)
            owner_id = ForeignKey("TaskA")

        class TaskC(Model):
            _table_name = "task_c"
            id = IntField(primary_key=True)
            parent_id = ForeignKey("TaskB")

        Model.bind(db)
        Model.create_all_tables()

        a = TaskA(name="root")
        a.save()
        b = TaskB(owner_id=a.id)
        b.save()
        c = TaskC(parent_id=b.id)
        c.save()

        # Recreate must not fail
        Model.create_all_tables(recreate=True)

        tables = db.fetchall(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        )
        table_names = [t["name"] for t in tables]
        assert "task_a" in table_names
        assert "task_b" in table_names
        assert "task_c" in table_names
        db.close()

    def test_create_tables_basic(self):
        """Basic create_all_tables without recreate should work."""
        db = make_db()

        class Author(Model):
            id = IntField(primary_key=True)
            name = StringField()

        class Book(Model):
            id = IntField(primary_key=True)
            title = StringField()
            author_id = ForeignKey("Author")

        Model.bind(db)
        Model.create_all_tables()

        a = Author(name="Orwell")
        a.save()
        Book(title="1984", author_id=a.id).save()

        books = db.fetchall("SELECT * FROM books")
        assert len(books) == 1
        db.close()


# ══════════════════════════════════════════
# 5. Foreign Key - Lazy Loading
# ══════════════════════════════════════════

class TestForeignKeyLazyLoad:
    def test_lazy_load_works(self):
        db = make_db()

        class Author(Model):
            id = IntField(primary_key=True)
            name = StringField()

        class Book(Model):
            id = IntField(primary_key=True)
            title = StringField()
            author_id = ForeignKey("Author")

        Model.bind(db)
        Model.create_all_tables()

        a = Author(name="Tolkien")
        a.save()
        b = Book(title="The Hobbit", author_id=a.id)
        b.save()

        related = b.get_related("author_id")
        assert related is not None
        assert related.name == "Tolkien"
        db.close()

    def test_lazy_load_after_close_raises_clear_error(self):
        """Accessing FK after db.close() should raise a clear ConnectionError,
        not an internal sqlite3 error or AttributeError."""
        db = make_db()

        class Author(Model):
            id = IntField(primary_key=True)
            name = StringField()

        class Book(Model):
            id = IntField(primary_key=True)
            title = StringField()
            author_id = ForeignKey("Author")

        Model.bind(db)
        Model.create_all_tables()

        a = Author(name="Tolkien")
        a.save()
        b = Book(title="The Hobbit", author_id=a.id)
        b.save()

        db.close()

        with pytest.raises(ConnectionError, match="closed"):
            b.get_related("author_id")

    def test_lazy_load_returns_none_for_null_fk(self):
        db = make_db()

        class Author(Model):
            id = IntField(primary_key=True)
            name = StringField()

        class Book(Model):
            id = IntField(primary_key=True)
            title = StringField()
            author_id = ForeignKey("Author")

        Model.bind(db)
        Model.create_all_tables()

        b = Book(title="Anonymous", author_id=None)
        b.save()

        related = b.get_related("author_id")
        assert related is None
        db.close()


# ══════════════════════════════════════════
# 6. QuerySet - Basic
# ══════════════════════════════════════════

class TestQuerySetBasic:
    def test_all(self):
        db = make_db()

        class Item(Model):
            id = IntField(primary_key=True)
            name = StringField()

        Model.bind(db)
        Item.create_table()

        Item(name="A").save()
        Item(name="B").save()
        Item(name="C").save()

        qs = QuerySet(Item)
        results = qs.all()
        assert len(results) == 3
        db.close()

    def test_filter_single(self):
        db = make_db()

        class Item(Model):
            id = IntField(primary_key=True)
            name = StringField()
            price = IntField()

        Model.bind(db)
        Item.create_table()

        Item(name="A", price=10).save()
        Item(name="B", price=20).save()
        Item(name="C", price=10).save()

        results = QuerySet(Item).filter(price=10).all()
        assert len(results) == 2
        db.close()

    def test_filter_with_lookup(self):
        db = make_db()

        class Item(Model):
            id = IntField(primary_key=True)
            price = IntField()

        Model.bind(db)
        Item.create_table()

        Item(price=5).save()
        Item(price=15).save()
        Item(price=25).save()

        results = QuerySet(Item).filter(price__gt=10).all()
        assert len(results) == 2
        db.close()

    def test_exclude(self):
        db = make_db()

        class Item(Model):
            id = IntField(primary_key=True)
            name = StringField()

        Model.bind(db)
        Item.create_table()

        Item(name="A").save()
        Item(name="B").save()
        Item(name="C").save()

        results = QuerySet(Item).exclude(name="B").all()
        assert len(results) == 2
        names = {r.name for r in results}
        assert "B" not in names
        db.close()

    def test_order_by_asc(self):
        db = make_db()

        class Item(Model):
            id = IntField(primary_key=True)
            price = IntField()

        Model.bind(db)
        Item.create_table()

        Item(price=30).save()
        Item(price=10).save()
        Item(price=20).save()

        results = QuerySet(Item).order_by("price").all()
        prices = [r.price for r in results]
        assert prices == [10, 20, 30]
        db.close()

    def test_order_by_desc(self):
        db = make_db()

        class Item(Model):
            id = IntField(primary_key=True)
            price = IntField()

        Model.bind(db)
        Item.create_table()

        Item(price=30).save()
        Item(price=10).save()
        Item(price=20).save()

        results = QuerySet(Item).order_by("-price").all()
        prices = [r.price for r in results]
        assert prices == [30, 20, 10]
        db.close()

    def test_limit_and_offset(self):
        db = make_db()

        class Item(Model):
            id = IntField(primary_key=True)
            seq = IntField()

        Model.bind(db)
        Item.create_table()

        for i in range(10):
            Item(seq=i).save()

        results = QuerySet(Item).order_by("seq").limit(3).offset(2).all()
        seqs = [r.seq for r in results]
        assert seqs == [2, 3, 4]
        db.close()

    def test_count(self):
        db = make_db()

        class Item(Model):
            id = IntField(primary_key=True)
            name = StringField()

        Model.bind(db)
        Item.create_table()

        Item(name="A").save()
        Item(name="B").save()

        count = QuerySet(Item).count()
        assert count == 2
        db.close()

    def test_first(self):
        db = make_db()

        class Item(Model):
            id = IntField(primary_key=True)
            name = StringField()

        Model.bind(db)
        Item.create_table()

        Item(name="First").save()
        Item(name="Second").save()

        item = QuerySet(Item).order_by("id").first()
        assert item.name == "First"
        db.close()

    def test_first_empty(self):
        db = make_db()

        class Item(Model):
            id = IntField(primary_key=True)
            name = StringField()

        Model.bind(db)
        Item.create_table()

        item = QuerySet(Item).first()
        assert item is None
        db.close()


# ══════════════════════════════════════════
# 7. QuerySet - Chained Filters
# ══════════════════════════════════════════

class TestChainedFilters:
    def test_chained_filter_produces_valid_sql(self):
        """filter().filter() must produce a single WHERE with AND,
        not multiple WHERE clauses."""
        db = make_db()

        class Item(Model):
            id = IntField(primary_key=True)
            name = StringField()
            price = IntField()
            category = StringField()

        Model.bind(db)
        Item.create_table()

        Item(name="A", price=10, category="food").save()
        Item(name="B", price=20, category="food").save()
        Item(name="C", price=10, category="tech").save()
        Item(name="D", price=20, category="tech").save()

        # Chain two filter calls — must AND them
        results = (
            QuerySet(Item)
            .filter(price=10)
            .filter(category="food")
            .all()
        )
        assert len(results) == 1
        assert results[0].name == "A"
        db.close()

    def test_chained_filter_with_lookups(self):
        """Chaining filter with __ lookups must also produce valid SQL."""
        db = make_db()

        class Item(Model):
            id = IntField(primary_key=True)
            price = IntField()
            stock = IntField()

        Model.bind(db)
        Item.create_table()

        Item(price=5, stock=100).save()
        Item(price=15, stock=50).save()
        Item(price=25, stock=200).save()
        Item(price=35, stock=10).save()

        results = (
            QuerySet(Item)
            .filter(price__gt=10)
            .filter(stock__gte=50)
            .all()
        )
        assert len(results) == 2  # price=15,stock=50 and price=25,stock=200
        db.close()

    def test_single_filter_multiple_conditions(self):
        """Single filter with multiple kwargs should also work."""
        db = make_db()

        class Item(Model):
            id = IntField(primary_key=True)
            name = StringField()
            price = IntField()

        Model.bind(db)
        Item.create_table()

        Item(name="A", price=10).save()
        Item(name="B", price=20).save()
        Item(name="A", price=20).save()

        results = QuerySet(Item).filter(name="A", price=10).all()
        assert len(results) == 1
        db.close()


# ══════════════════════════════════════════
# 8. Aggregate + GROUP BY
# ══════════════════════════════════════════

class TestAggregateGroupBy:
    def test_simple_aggregate_sum(self):
        db = make_db()

        class Sale(Model):
            id = IntField(primary_key=True)
            amount = IntField()

        Model.bind(db)
        Sale.create_table()

        Sale(amount=100).save()
        Sale(amount=200).save()
        Sale(amount=300).save()

        total = QuerySet(Sale).aggregate("sum", "amount").execute()
        assert total == 600
        db.close()

    def test_simple_aggregate_avg(self):
        db = make_db()

        class Sale(Model):
            id = IntField(primary_key=True)
            amount = IntField()

        Model.bind(db)
        Sale.create_table()

        Sale(amount=10).save()
        Sale(amount=20).save()
        Sale(amount=30).save()

        avg = QuerySet(Sale).aggregate("avg", "amount").execute()
        assert abs(avg - 20.0) < 0.01
        db.close()

    def test_aggregate_with_group_by(self):
        """aggregate + group_by must produce valid SQL:
        SELECT category, AVG(price) FROM ... GROUP BY category"""
        db = make_db()

        class Product(Model):
            id = IntField(primary_key=True)
            category = StringField()
            price = IntField()

        Model.bind(db)
        Product.create_table()

        Product(category="food", price=10).save()
        Product(category="food", price=20).save()
        Product(category="tech", price=100).save()
        Product(category="tech", price=200).save()

        results = (
            QuerySet(Product)
            .aggregate("avg", "price")
            .group_by("category")
            .execute()
        )

        assert isinstance(results, list)
        assert len(results) == 2

        result_dict = {r["category"]: r for r in results}
        food_avg = list(result_dict["food"].values())[-1]
        tech_avg = list(result_dict["tech"].values())[-1]
        assert abs(food_avg - 15.0) < 0.01
        assert abs(tech_avg - 150.0) < 0.01
        db.close()

    def test_aggregate_group_by_with_filter(self):
        """Group-by aggregate with a WHERE filter must work.
        SQL should be: SELECT ... FROM ... WHERE ... GROUP BY ..."""
        db = make_db()

        class Product(Model):
            id = IntField(primary_key=True)
            category = StringField()
            price = IntField()
            active = BoolField()

        Model.bind(db)
        Product.create_table()

        Product(category="food", price=10, active=1).save()
        Product(category="food", price=20, active=0).save()
        Product(category="tech", price=100, active=1).save()
        Product(category="tech", price=200, active=1).save()

        results = (
            QuerySet(Product)
            .filter(active=1)
            .aggregate("sum", "price")
            .group_by("category")
            .execute()
        )

        assert isinstance(results, list)
        result_dict = {r["category"]: r for r in results}
        food_sum = list(result_dict["food"].values())[-1]
        tech_sum = list(result_dict["tech"].values())[-1]
        assert food_sum == 10   # only the active food item
        assert tech_sum == 300  # both tech items are active
        db.close()

    def test_aggregate_count_with_group_by(self):
        db = make_db()

        class Product(Model):
            id = IntField(primary_key=True)
            category = StringField()

        Model.bind(db)
        Product.create_table()

        Product(category="A").save()
        Product(category="A").save()
        Product(category="B").save()

        results = (
            QuerySet(Product)
            .aggregate("count", "*")
            .group_by("category")
            .execute()
        )

        result_dict = {r["category"]: r for r in results}
        assert list(result_dict["A"].values())[-1] == 2
        assert list(result_dict["B"].values())[-1] == 1
        db.close()


# ══════════════════════════════════════════
# 9. Select Related (Eager Loading)
# ══════════════════════════════════════════

class TestSelectRelated:
    def test_select_related_basic(self):
        db = make_db()

        class Author(Model):
            id = IntField(primary_key=True)
            name = StringField()

        class Book(Model):
            id = IntField(primary_key=True)
            title = StringField()
            author_id = ForeignKey("Author")

        Model.bind(db)
        Model.create_all_tables()

        a = Author(name="Orwell")
        a.save()
        Book(title="1984", author_id=a.id).save()

        results = QuerySet(Book).select_related("author_id").all()
        assert len(results) == 1
        assert results[0].title == "1984"
        db.close()


# ══════════════════════════════════════════
# 10. Integration
# ══════════════════════════════════════════

class TestIntegration:
    def test_full_workflow(self):
        """End-to-end: define models, create tables, CRUD, query."""
        db = make_db()

        class Category(Model):
            id = IntField(primary_key=True)
            name = StringField()

        class Product(Model):
            id = IntField(primary_key=True)
            name = StringField()
            price = FloatField()
            category_id = ForeignKey("Category")
            active = BoolField(default=True)

        Model.bind(db)
        Model.create_all_tables()

        cat = Category(name="Electronics")
        cat.save()

        Product(name="Phone", price=999.99, category_id=cat.id, active=1).save()
        Product(name="Laptop", price=1999.99, category_id=cat.id, active=1).save()
        Product(name="Cable", price=9.99, category_id=cat.id, active=0).save()

        # Chained filter
        active_expensive = (
            QuerySet(Product)
            .filter(active=1)
            .filter(price__gt=500)
            .order_by("-price")
            .all()
        )
        assert len(active_expensive) == 2
        assert active_expensive[0].name == "Laptop"
        assert active_expensive[1].name == "Phone"

        # Count
        total = QuerySet(Product).count()
        assert total == 3

        # Aggregate
        total_price = QuerySet(Product).aggregate("sum", "price").execute()
        assert abs(total_price - 3009.97) < 0.01

        db.close()

    def test_multiple_models_with_fk_chain(self):
        """Three models with FK chain: Comment -> Post -> User."""
        db = make_db()

        class Comment(Model):
            id = IntField(primary_key=True)
            text = StringField()
            post_id = ForeignKey("Post")

        class Post(Model):
            id = IntField(primary_key=True)
            title = StringField()
            user_id = ForeignKey("BlogUser")

        class BlogUser(Model):
            id = IntField(primary_key=True)
            name = StringField()

        Model.bind(db)
        Model.create_all_tables()

        user = BlogUser(name="Alice")
        user.save()
        post = Post(title="Hello World", user_id=user.id)
        post.save()
        comment = Comment(text="Nice post!", post_id=post.id)
        comment.save()

        # Verify FK lazy load
        related_post = comment.get_related("post_id")
        assert related_post.title == "Hello World"

        related_user = post.get_related("user_id")
        assert related_user.name == "Alice"

        db.close()
