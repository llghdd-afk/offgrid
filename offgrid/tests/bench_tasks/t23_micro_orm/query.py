"""Chain query builder for micro ORM."""

from model import _model_registry


class QuerySet:
    """Chainable query builder that generates SQL for a given model."""

    def __init__(self, model_cls):
        self.model_cls = model_cls
        self._filters = []
        self._excludes = []
        self._order = []
        self._limit_val = None
        self._offset_val = None
        self._group_by_cols = []
        self._aggregate_func = None
        self._aggregate_col = None
        self._select_related_fields = []

    def _clone(self):
        """Create a copy of this queryset for chaining."""
        qs = QuerySet(self.model_cls)
        qs._filters = list(self._filters)
        qs._excludes = list(self._excludes)
        qs._order = list(self._order)
        qs._limit_val = self._limit_val
        qs._offset_val = self._offset_val
        qs._group_by_cols = list(self._group_by_cols)
        qs._aggregate_func = self._aggregate_func
        qs._aggregate_col = self._aggregate_col
        qs._select_related_fields = list(self._select_related_fields)
        return qs

    def filter(self, **kwargs):
        """Add AND filter conditions."""
        qs = self._clone()
        qs._filters.append(kwargs)
        return qs

    def exclude(self, **kwargs):
        """Add exclusion conditions (NOT)."""
        qs = self._clone()
        qs._excludes.append(kwargs)
        return qs

    def order_by(self, *fields):
        """Set ordering. Prefix with '-' for DESC."""
        qs = self._clone()
        qs._order = list(fields)
        return qs

    def limit(self, n):
        qs = self._clone()
        qs._limit_val = n
        return qs

    def offset(self, n):
        qs = self._clone()
        qs._offset_val = n
        return qs

    def group_by(self, *columns):
        qs = self._clone()
        qs._group_by_cols = list(columns)
        return qs

    def aggregate(self, func, column):
        """Set an aggregate function: count, sum, avg, min, max."""
        qs = self._clone()
        qs._aggregate_func = func.upper()
        qs._aggregate_col = column
        return qs

    def select_related(self, *fk_fields):
        """Eager-load related objects via JOIN."""
        qs = self._clone()
        qs._select_related_fields = list(fk_fields)
        return qs

    def _build_where(self):
        """Build WHERE clause from filters and excludes."""
        parts = []
        params = []

        for f_dict in self._filters:
            conditions = []
            for key, val in f_dict.items():
                if '__' in key:
                    field_name, op = key.rsplit('__', 1)
                    if op == 'gt':
                        conditions.append(f"{field_name} > ?")
                    elif op == 'lt':
                        conditions.append(f"{field_name} < ?")
                    elif op == 'gte':
                        conditions.append(f"{field_name} >= ?")
                    elif op == 'lte':
                        conditions.append(f"{field_name} <= ?")
                    elif op == 'ne':
                        conditions.append(f"{field_name} != ?")
                    elif op == 'like':
                        conditions.append(f"{field_name} LIKE ?")
                    else:
                        conditions.append(f"{key} = ?")
                else:
                    conditions.append(f"{key} = ?")
                params.append(val)
            parts.append(f"({' AND '.join(conditions)})")

        for e_dict in self._excludes:
            for key, val in e_dict.items():
                parts.append(f"NOT ({key} = ?)")
                params.append(val)

        # Build WHERE from parts
        where_clauses = []
        for part in parts:
            where_clauses.append(f"WHERE {part}")

        return ' '.join(where_clauses), params

    def _build_sql(self):
        """Build the complete SQL query."""
        table = self.model_cls.table_name()

        # SELECT clause
        if self._aggregate_func:
            if self._group_by_cols:
                group_cols = ', '.join(self._group_by_cols)
                select = f"SELECT {group_cols}, {self._aggregate_func}({self._aggregate_col})"
            else:
                select = f"SELECT {self._aggregate_func}({self._aggregate_col})"
        elif self._select_related_fields:
            select = self._build_select_related()
        else:
            select = f"SELECT *"

        # FROM clause
        from_clause = f"FROM {table}"

        # JOIN clause for select_related
        join_clause = ""
        if self._select_related_fields:
            join_clause = self._build_joins()

        # WHERE clause
        where_clause, params = self._build_where()

        # GROUP BY
        group_clause = ""
        if self._group_by_cols:
            group_clause = f"GROUP BY {', '.join(self._group_by_cols)}"

        # ORDER BY
        order_clause = ""
        if self._order:
            order_parts = []
            for f in self._order:
                if f.startswith('-'):
                    order_parts.append(f"{f[1:]} DESC")
                else:
                    order_parts.append(f"{f} ASC")
            order_clause = f"ORDER BY {', '.join(order_parts)}"

        # LIMIT / OFFSET
        limit_clause = f"LIMIT {self._limit_val}" if self._limit_val else ""
        offset_clause = f"OFFSET {self._offset_val}" if self._offset_val else ""

        # Assemble query parts
        sql_parts = [
            select, from_clause, join_clause,
            group_clause, where_clause,
            order_clause, limit_clause, offset_clause
        ]

        sql = ' '.join(p for p in sql_parts if p)
        return sql, params

    def _build_select_related(self):
        """Build SELECT with joined table columns."""
        table = self.model_cls.table_name()
        cols = [f"{table}.*"]
        for fk_name in self._select_related_fields:
            field = self.model_cls._fields.get(fk_name)
            if field:
                from model import ForeignKey
                if isinstance(field, ForeignKey):
                    ref_cls = _model_registry.get(field.reference_model)
                    if ref_cls:
                        ref_table = ref_cls.table_name()
                        for rf_name in ref_cls._fields:
                            cols.append(f"{ref_table}.{rf_name} AS {ref_table}_{rf_name}")
        return f"SELECT {', '.join(cols)}"

    def _build_joins(self):
        """Build JOIN clauses for select_related."""
        table = self.model_cls.table_name()
        joins = []
        for fk_name in self._select_related_fields:
            field = self.model_cls._fields.get(fk_name)
            if field:
                from model import ForeignKey
                if isinstance(field, ForeignKey):
                    ref_cls = _model_registry.get(field.reference_model)
                    if ref_cls:
                        ref_table = ref_cls.table_name()
                        ref_pk = None
                        for rf_name, rf in ref_cls._fields.items():
                            if rf.primary_key:
                                ref_pk = rf_name
                                break
                        if ref_pk:
                            joins.append(
                                f"LEFT JOIN {ref_table} ON "
                                f"{table}.{fk_name} = {ref_table}.{ref_pk}"
                            )
        return ' '.join(joins)

    def execute(self):
        """Execute the query and return results."""
        sql, params = self._build_sql()
        db = self.model_cls._db
        rows = db.fetchall(sql, params)

        if self._aggregate_func and not self._group_by_cols:
            # Return scalar value for simple aggregates
            if rows:
                return list(rows[0].values())[0]
            return None

        if self._aggregate_func and self._group_by_cols:
            # Return list of dicts for grouped aggregates
            return rows

        # Construct model instances
        results = []
        for row in rows:
            # Filter out joined columns for the main model
            model_data = {}
            for fname in self.model_cls._fields:
                if fname in row:
                    model_data[fname] = row[fname]
            obj = self.model_cls(**model_data)
            results.append(obj)

        return results

    def count(self):
        """Shortcut for COUNT(*)."""
        return self.aggregate("COUNT", "*").execute()

    def all(self):
        """Return all matching records."""
        return self.execute()

    def first(self):
        """Return the first matching record."""
        results = self.limit(1).execute()
        return results[0] if results else None
