"""Model definition and field mapping for micro ORM."""

from connection import Database


# ── Field Types ──

class Field:
    """Base field descriptor."""

    def __init__(self, primary_key=False, default=None, nullable=True):
        self.primary_key = primary_key
        self.default = default
        self.nullable = nullable
        self.name = None  # set by metaclass

    def sql_type(self):
        raise NotImplementedError


class IntField(Field):
    def sql_type(self):
        return "INTEGER"


class StringField(Field):
    def __init__(self, max_length=255, **kwargs):
        super().__init__(**kwargs)
        self.max_length = max_length

    def sql_type(self):
        return "TEXT"


class FloatField(Field):
    def sql_type(self):
        return "FLOAT"


class BoolField(Field):
    def sql_type(self):
        return "INTEGER"  # SQLite stores bools as 0/1


class ForeignKey(Field):
    """Foreign key field with lazy loading."""

    def __init__(self, reference_model, **kwargs):
        super().__init__(**kwargs)
        self.reference_model = reference_model  # string name like "User"
        self._cache = {}

    def sql_type(self):
        return "INTEGER"


# ── Metaclass ──

_model_registry = {}


class ModelMeta(type):
    """Metaclass that registers fields and builds table schema."""

    def __new__(mcs, name, bases, namespace):
        fields = {}
        for key, val in list(namespace.items()):
            if isinstance(val, Field):
                val.name = key
                fields[key] = val
        namespace['_fields'] = fields
        cls = super().__new__(mcs, name, bases, namespace)
        if name != 'Model':
            _model_registry[name] = cls
        return cls


# ── Base Model ──

class Model(metaclass=ModelMeta):
    """Base model with CRUD operations."""

    _db = None  # set via Model.bind(db)
    _table_name = None

    @classmethod
    def bind(cls, db):
        """Bind a database connection to all models."""
        Model._db = db

    @classmethod
    def table_name(cls):
        if cls._table_name:
            return cls._table_name
        return cls.__name__.lower() + 's'

    @classmethod
    def create_table(cls):
        """Generate and execute CREATE TABLE statement."""
        columns = []
        fk_constraints = []
        for fname, field in cls._fields.items():
            col_def = f"{fname} {field.sql_type()}"
            if field.primary_key:
                col_def += " PRIMARY KEY AUTOINCREMENT"
            if not field.nullable and not field.primary_key:
                col_def += " NOT NULL"
            columns.append(col_def)

            if isinstance(field, ForeignKey):
                ref_cls = _model_registry.get(field.reference_model)
                if ref_cls:
                    ref_pk = None
                    for rf_name, rf in ref_cls._fields.items():
                        if rf.primary_key:
                            ref_pk = rf_name
                            break
                    if ref_pk:
                        fk_constraints.append(
                            f"FOREIGN KEY ({fname}) REFERENCES "
                            f"{ref_cls.table_name()}({ref_pk})"
                        )

        all_parts = columns + fk_constraints
        sql = f"CREATE TABLE IF NOT EXISTS {cls.table_name()} ({', '.join(all_parts)})"
        cls._db.execute(sql)

    @classmethod
    def drop_table(cls):
        """Drop this model's table."""
        cls._db.execute(f"DROP TABLE IF EXISTS {cls.table_name()}")

    @classmethod
    def create_all_tables(cls, recreate=False):
        """Create tables for all registered models.

        Args:
            recreate: If True, drop existing tables first (for migration).
        """
        if recreate:
            # Drop tables in registry order (same as creation order)
            for model_name, model_cls in _model_registry.items():
                model_cls.drop_table()
            cls._db.commit()

        for model_name, model_cls in _model_registry.items():
            model_cls.create_table()

    def __init__(self, **kwargs):
        for fname, field in self._fields.items():
            if fname in kwargs:
                setattr(self, fname, kwargs[fname])
            elif field.default is not None:
                setattr(self, fname, field.default() if callable(field.default) else field.default)
            elif field.primary_key:
                setattr(self, fname, None)
            else:
                setattr(self, fname, None)

    def save(self):
        """Insert or update this instance."""
        pk_field = None
        pk_value = None
        for fname, field in self._fields.items():
            if field.primary_key:
                pk_field = fname
                pk_value = getattr(self, fname)
                break

        data = {}
        for fname in self._fields:
            if fname == pk_field and pk_value is None:
                continue  # skip auto-increment on insert
            data[fname] = getattr(self, fname)

        if pk_value is None:
            # INSERT
            cols = ', '.join(data.keys())
            placeholders = ', '.join(['?'] * len(data))
            sql = f"INSERT INTO {self.table_name()} ({cols}) VALUES ({placeholders})"
            cursor = self._db.execute(sql, list(data.values()))
            setattr(self, pk_field, cursor.lastrowid)
        else:
            # UPDATE
            set_clause = ', '.join(f"{k} = ?" for k in data if k != pk_field)
            vals = [v for k, v in data.items() if k != pk_field]
            vals.append(pk_value)
            sql = f"UPDATE {self.table_name()} SET {set_clause} WHERE {pk_field} = ?"
            self._db.execute(sql, vals)

        self._db.commit()

    def delete(self):
        """Delete this instance from the database."""
        pk_field = None
        pk_value = None
        for fname, field in self._fields.items():
            if field.primary_key:
                pk_field = fname
                pk_value = getattr(self, fname)
                break

        if pk_value is not None:
            sql = f"DELETE FROM {self.table_name()} WHERE {pk_field} = ?"
            self._db.execute(sql, [pk_value])
            self._db.commit()

    def refresh(self):
        """Reload this instance from the database."""
        pk_field = None
        pk_value = None
        for fname, field in self._fields.items():
            if field.primary_key:
                pk_field = fname
                pk_value = getattr(self, fname)
                break

        row = self._db.fetchone(
            f"SELECT * FROM {self.table_name()} WHERE {pk_field} = ?",
            [pk_value]
        )
        if row:
            for fname in self._fields:
                setattr(self, fname, row[fname])

    def get_related(self, fk_field_name):
        """Lazy-load a related object via foreign key."""
        field = self._fields.get(fk_field_name)
        if not isinstance(field, ForeignKey):
            raise ValueError(f"{fk_field_name} is not a ForeignKey")

        fk_value = getattr(self, fk_field_name)
        if fk_value is None:
            return None

        ref_cls = _model_registry.get(field.reference_model)
        if ref_cls is None:
            raise ValueError(f"Unknown model: {field.reference_model}")

        ref_pk = None
        for rf_name, rf in ref_cls._fields.items():
            if rf.primary_key:
                ref_pk = rf_name
                break

        row = self._db.fetchone(
            f"SELECT * FROM {ref_cls.table_name()} WHERE {ref_pk} = ?",
            [fk_value]
        )
        if row:
            return ref_cls(**row)
        return None
