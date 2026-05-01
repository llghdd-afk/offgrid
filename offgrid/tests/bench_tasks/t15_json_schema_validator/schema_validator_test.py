"""
Tests for JSON Schema Validator.
Tests cover all validation features and edge cases.
DO NOT MODIFY THIS FILE.
"""

import unittest
import sys

from schema_validator import SchemaValidator, ValidationError, validate


class TestBasicTypeValidation(unittest.TestCase):
    """Test basic type checking."""

    def test_string_type(self):
        valid, errors = validate({"type": "string"}, "hello")
        self.assertTrue(valid)

    def test_string_type_fail(self):
        valid, errors = validate({"type": "string"}, 42)
        self.assertFalse(valid)

    def test_integer_type(self):
        valid, errors = validate({"type": "integer"}, 42)
        self.assertTrue(valid)

    def test_integer_rejects_float(self):
        valid, errors = validate({"type": "integer"}, 3.14)
        self.assertFalse(valid)

    def test_number_accepts_int_and_float(self):
        valid1, _ = validate({"type": "number"}, 42)
        valid2, _ = validate({"type": "number"}, 3.14)
        self.assertTrue(valid1)
        self.assertTrue(valid2)

    def test_boolean_type(self):
        valid, _ = validate({"type": "boolean"}, True)
        self.assertTrue(valid)

    def test_boolean_not_integer(self):
        """Booleans should not pass as integers."""
        valid, _ = validate({"type": "integer"}, True)
        self.assertFalse(valid)

    def test_null_type(self):
        valid, _ = validate({"type": "null"}, None)
        self.assertTrue(valid)

    def test_object_type(self):
        valid, _ = validate({"type": "object"}, {"a": 1})
        self.assertTrue(valid)

    def test_array_type(self):
        valid, _ = validate({"type": "array"}, [1, 2, 3])
        self.assertTrue(valid)


class TestStringValidation(unittest.TestCase):
    """Test string-specific constraints."""

    def test_min_length(self):
        schema = {"type": "string", "minLength": 3}
        valid, _ = validate(schema, "ab")
        self.assertFalse(valid)

    def test_max_length(self):
        schema = {"type": "string", "maxLength": 5}
        valid, _ = validate(schema, "toolong")
        self.assertFalse(valid)

    def test_length_in_range(self):
        schema = {"type": "string", "minLength": 2, "maxLength": 5}
        valid, _ = validate(schema, "ok")
        self.assertTrue(valid)

    def test_pattern_match(self):
        schema = {"type": "string", "pattern": r"^\d{3}-\d{4}$"}
        valid, _ = validate(schema, "123-4567")
        self.assertTrue(valid)

    def test_pattern_no_match(self):
        schema = {"type": "string", "pattern": r"^\d{3}-\d{4}$"}
        valid, _ = validate(schema, "abc-defg")
        self.assertFalse(valid)


class TestNumberValidation(unittest.TestCase):
    """Test number-specific constraints."""

    def test_minimum(self):
        schema = {"type": "number", "minimum": 0}
        valid, _ = validate(schema, -1)
        self.assertFalse(valid)

    def test_maximum(self):
        schema = {"type": "number", "maximum": 100}
        valid, _ = validate(schema, 101)
        self.assertFalse(valid)

    def test_in_range(self):
        schema = {"type": "integer", "minimum": 1, "maximum": 10}
        valid, _ = validate(schema, 5)
        self.assertTrue(valid)


class TestEnumValidation(unittest.TestCase):
    """Test enum constraints."""

    def test_valid_enum(self):
        schema = {"enum": ["red", "green", "blue"]}
        valid, _ = validate(schema, "green")
        self.assertTrue(valid)

    def test_invalid_enum(self):
        schema = {"enum": ["red", "green", "blue"]}
        valid, _ = validate(schema, "yellow")
        self.assertFalse(valid)

    def test_enum_with_mixed_types(self):
        schema = {"enum": [1, "one", True, None]}
        valid1, _ = validate(schema, 1)
        valid2, _ = validate(schema, "one")
        self.assertTrue(valid1)
        self.assertTrue(valid2)


class TestObjectValidation(unittest.TestCase):
    """Test object validation with required fields and properties."""

    def test_required_fields_present(self):
        schema = {
            "type": "object",
            "required": ["name", "age"],
            "properties": {
                "name": {"type": "string"},
                "age": {"type": "integer"},
            },
        }
        valid, _ = validate(schema, {"name": "Alice", "age": 30})
        self.assertTrue(valid)

    def test_required_field_missing(self):
        schema = {
            "type": "object",
            "required": ["name", "age"],
            "properties": {
                "name": {"type": "string"},
                "age": {"type": "integer"},
            },
        }
        valid, errors = validate(schema, {"name": "Alice"})
        self.assertFalse(valid)
        self.assertEqual(len(errors), 1)
        self.assertIn("age", errors[0].path)

    def test_property_type_validation(self):
        schema = {
            "type": "object",
            "properties": {
                "count": {"type": "integer"},
            },
        }
        valid, _ = validate(schema, {"count": "not_a_number"})
        self.assertFalse(valid)

    def test_nested_object_required_fields(self):
        """BUG3 trigger: nested objects should validate their OWN required fields,
        not the root schema's required fields."""
        schema = {
            "type": "object",
            "required": ["name"],
            "properties": {
                "name": {"type": "string"},
                "address": {
                    "type": "object",
                    "required": ["street", "city"],
                    "properties": {
                        "street": {"type": "string"},
                        "city": {"type": "string"},
                        "zip": {"type": "string"},
                    },
                },
            },
        }
        # address is present but missing required fields 'street' and 'city'
        valid, errors = validate(schema, {
            "name": "Alice",
            "address": {"zip": "12345"},
        })
        self.assertFalse(valid)
        error_paths = [e.path for e in errors]
        self.assertIn("address.street", error_paths)
        self.assertIn("address.city", error_paths)

    def test_deeply_nested_required(self):
        """Deeply nested objects each have their own required fields."""
        schema = {
            "type": "object",
            "required": ["level1"],
            "properties": {
                "level1": {
                    "type": "object",
                    "required": ["level2"],
                    "properties": {
                        "level2": {
                            "type": "object",
                            "required": ["value"],
                            "properties": {
                                "value": {"type": "string"},
                            },
                        },
                    },
                },
            },
        }
        valid, errors = validate(schema, {"level1": {"level2": {}}})
        self.assertFalse(valid)
        error_paths = [e.path for e in errors]
        self.assertIn("level1.level2.value", error_paths)


class TestArrayValidation(unittest.TestCase):
    """Test array validation with items, minItems, maxItems."""

    def test_valid_array_items(self):
        schema = {"type": "array", "items": {"type": "integer"}}
        valid, _ = validate(schema, [1, 2, 3])
        self.assertTrue(valid)

    def test_invalid_array_item(self):
        schema = {"type": "array", "items": {"type": "integer"}}
        valid, _ = validate(schema, [1, "two", 3])
        self.assertFalse(valid)

    def test_min_items(self):
        schema = {"type": "array", "minItems": 2}
        valid, _ = validate(schema, [1])
        self.assertFalse(valid)

    def test_max_items(self):
        schema = {"type": "array", "maxItems": 3}
        valid, _ = validate(schema, [1, 2, 3, 4])
        self.assertFalse(valid)

    def test_max_items_exact_boundary(self):
        """BUG4 trigger: an array with exactly maxItems elements should be VALID.
        maxItems means 'at most N items', so N items is allowed."""
        schema = {"type": "array", "maxItems": 3}
        valid, _ = validate(schema, [1, 2, 3])
        self.assertTrue(valid)

    def test_max_items_one_over(self):
        """One more than maxItems should be invalid."""
        schema = {"type": "array", "maxItems": 2}
        valid, errors = validate(schema, [1, 2, 3])
        self.assertFalse(valid)

    def test_items_empty_schema_means_any_type(self):
        """items: {} means 'validate each item against empty schema'
        (any type is valid). Combined with minItems/maxItems, the
        validation must still work correctly."""
        schema = {
            "type": "array",
            "items": {},
            "minItems": 2,
            "maxItems": 4,
        }
        # Valid: 3 items within [2, 4] range
        valid1, _ = validate(schema, [1, "two", None])
        self.assertTrue(valid1)

        # Invalid: 1 item, below minItems=2
        valid2, errors2 = validate(schema, [1])
        self.assertFalse(valid2)

        # Invalid: 5 items, above maxItems=4
        valid3, errors3 = validate(schema, [1, 2, 3, 4, 5])
        self.assertFalse(valid3)

    def test_items_empty_schema_with_max_items(self):
        """When items is {}, array length constraints must still apply."""
        schema = {
            "type": "array",
            "items": {},
            "maxItems": 2,
        }
        # 3 items exceeds maxItems=2
        valid, errors = validate(schema, [{"a": 1}, {"b": 2}, {"c": 3}])
        self.assertFalse(valid)
        self.assertTrue(any("maxItems" in e.message for e in errors))


class TestRefValidation(unittest.TestCase):
    """Test $ref resolution."""

    def test_basic_ref(self):
        schema = {
            "type": "object",
            "properties": {
                "address": {"$ref": "#/definitions/Address"},
            },
            "definitions": {
                "Address": {
                    "type": "object",
                    "required": ["street"],
                    "properties": {
                        "street": {"type": "string"},
                        "city": {"type": "string"},
                    },
                },
            },
        }
        valid, _ = validate(schema, {
            "address": {"street": "123 Main St", "city": "Springfield"},
        })
        self.assertTrue(valid)

    def test_ref_validation_error(self):
        schema = {
            "type": "object",
            "properties": {
                "address": {"$ref": "#/definitions/Address"},
            },
            "definitions": {
                "Address": {
                    "type": "object",
                    "required": ["street"],
                    "properties": {
                        "street": {"type": "string"},
                    },
                },
            },
        }
        valid, errors = validate(schema, {"address": {}})
        self.assertFalse(valid)

    def test_circular_ref_does_not_hang(self):
        """BUG1 trigger: mutual circular $ref (A -> B -> A) should not cause
        infinite recursion. The validator should detect the cycle and stop."""
        schema = {
            "definitions": {
                "A": {"$ref": "#/definitions/B"},
                "B": {"$ref": "#/definitions/A"},
            },
            "$ref": "#/definitions/A",
        }
        # Should not raise RecursionError; should handle gracefully
        try:
            valid, errors = validate(schema, "anything")
            # If it returns without hanging, that's acceptable
        except RecursionError:
            self.fail("Circular $ref caused infinite recursion (RecursionError)")

    def test_circular_ref_self_reference(self):
        """A definition that directly references itself should not hang."""
        schema = {
            "definitions": {
                "Loop": {"$ref": "#/definitions/Loop"},
            },
            "$ref": "#/definitions/Loop",
        }
        try:
            valid, _ = validate(schema, {"key": "value"})
        except RecursionError:
            self.fail("Self-referencing $ref caused infinite recursion")

    def test_recursive_tree_schema(self):
        """Recursive tree schema (non-circular in data) should work correctly."""
        schema = {
            "definitions": {
                "Node": {
                    "type": "object",
                    "properties": {
                        "value": {"type": "integer"},
                        "child": {"$ref": "#/definitions/Node"},
                    },
                },
            },
            "$ref": "#/definitions/Node",
        }
        valid, _ = validate(schema, {
            "value": 1,
            "child": {"value": 2},
        })
        self.assertTrue(valid)

    def test_recursive_tree_with_type_error(self):
        """Recursive tree schema should still catch type errors in nested nodes."""
        schema = {
            "definitions": {
                "Node": {
                    "type": "object",
                    "properties": {
                        "value": {"type": "integer"},
                        "child": {"$ref": "#/definitions/Node"},
                    },
                },
            },
            "$ref": "#/definitions/Node",
        }
        valid, errors = validate(schema, {
            "value": 1,
            "child": {"value": "not_an_int"},
        })
        self.assertFalse(valid)


class TestOneOfValidation(unittest.TestCase):
    """Test oneOf combinator (exactly one must match)."""

    def test_oneof_single_match(self):
        schema = {
            "oneOf": [
                {"type": "string"},
                {"type": "integer"},
            ],
        }
        valid, _ = validate(schema, "hello")
        self.assertTrue(valid)

    def test_oneof_no_match(self):
        schema = {
            "oneOf": [
                {"type": "string"},
                {"type": "integer"},
            ],
        }
        valid, _ = validate(schema, [1, 2, 3])
        self.assertFalse(valid)

    def test_oneof_multiple_match_should_fail(self):
        """BUG2 trigger: oneOf means EXACTLY one must match.
        If value matches multiple schemas, it should fail."""
        schema = {
            "oneOf": [
                {"type": "number"},
                {"type": "integer"},
            ],
        }
        # 42 is both a number and an integer - should FAIL oneOf
        valid, errors = validate(schema, 42)
        self.assertFalse(valid)

    def test_oneof_overlapping_string_schemas(self):
        """Another overlapping oneOf case: both schemas match a short string."""
        schema = {
            "oneOf": [
                {"type": "string", "maxLength": 10},
                {"type": "string", "minLength": 1},
            ],
        }
        # "hello" matches both sub-schemas - should FAIL oneOf
        valid, _ = validate(schema, "hello")
        self.assertFalse(valid)

    def test_oneof_exactly_one_match_passes(self):
        """Only one schema matches => oneOf passes."""
        schema = {
            "oneOf": [
                {"type": "string", "minLength": 10},
                {"type": "string", "maxLength": 3},
            ],
        }
        # "hi" matches only maxLength<=3 (length 2), not minLength>=10
        valid, _ = validate(schema, "hi")
        self.assertTrue(valid)


class TestAnyOfValidation(unittest.TestCase):
    """Test anyOf combinator (at least one must match)."""

    def test_anyof_single_match(self):
        schema = {
            "anyOf": [
                {"type": "string"},
                {"type": "integer"},
            ],
        }
        valid, _ = validate(schema, 42)
        self.assertTrue(valid)

    def test_anyof_multiple_match_ok(self):
        """anyOf allows multiple matches - this is the key difference from oneOf."""
        schema = {
            "anyOf": [
                {"type": "number"},
                {"type": "integer"},
            ],
        }
        valid, _ = validate(schema, 42)
        self.assertTrue(valid)

    def test_anyof_no_match(self):
        schema = {
            "anyOf": [
                {"type": "string"},
                {"type": "integer"},
            ],
        }
        valid, _ = validate(schema, 3.14)
        self.assertFalse(valid)


class TestComplexSchema(unittest.TestCase):
    """Integration tests with complex real-world-like schemas."""

    def test_full_person_schema(self):
        """Complex schema combining multiple features."""
        schema = {
            "type": "object",
            "required": ["name", "age", "email"],
            "properties": {
                "name": {"type": "string", "minLength": 1, "maxLength": 100},
                "age": {"type": "integer", "minimum": 0, "maximum": 150},
                "email": {"type": "string", "pattern": r"^[\w.+-]+@[\w-]+\.[\w.]+$"},
                "role": {"enum": ["admin", "user", "guest"]},
                "address": {
                    "type": "object",
                    "required": ["country"],
                    "properties": {
                        "street": {"type": "string"},
                        "country": {"type": "string", "minLength": 2},
                    },
                },
                "tags": {
                    "type": "array",
                    "items": {"type": "string"},
                    "maxItems": 5,
                },
            },
        }

        valid_person = {
            "name": "Alice",
            "age": 30,
            "email": "alice@example.com",
            "role": "admin",
            "address": {"street": "123 Main", "country": "US"},
            "tags": ["dev", "lead"],
        }
        valid, _ = validate(schema, valid_person)
        self.assertTrue(valid)

    def test_full_person_schema_nested_required_fail(self):
        """Address is present but missing required 'country' field."""
        schema = {
            "type": "object",
            "required": ["name"],
            "properties": {
                "name": {"type": "string"},
                "address": {
                    "type": "object",
                    "required": ["country"],
                    "properties": {
                        "street": {"type": "string"},
                        "country": {"type": "string"},
                    },
                },
            },
        }
        valid, errors = validate(schema, {
            "name": "Bob",
            "address": {"street": "456 Oak"},
        })
        self.assertFalse(valid)
        self.assertTrue(any("country" in e.path for e in errors))

    def test_error_path_accuracy(self):
        """Verify error paths correctly reflect the nesting structure."""
        schema = {
            "type": "object",
            "properties": {
                "items": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "required": ["id"],
                        "properties": {
                            "id": {"type": "integer"},
                            "name": {"type": "string"},
                        },
                    },
                },
            },
        }
        valid, errors = validate(schema, {
            "items": [
                {"id": 1, "name": "ok"},
                {"name": "missing_id"},
                {"id": "wrong_type", "name": "bad"},
            ],
        })
        self.assertFalse(valid)
        error_paths = [e.path for e in errors]
        # Should have error for items[1].id (missing) and items[2].id (wrong type)
        self.assertTrue(any("items[1]" in p for p in error_paths))
        self.assertTrue(any("items[2]" in p for p in error_paths))


class TestConvenienceFunction(unittest.TestCase):
    """Test the top-level validate() convenience function."""

    def test_returns_tuple(self):
        result = validate({"type": "string"}, "hello")
        self.assertIsInstance(result, tuple)
        self.assertEqual(len(result), 2)

    def test_valid_returns_true_empty_errors(self):
        valid, errors = validate({"type": "integer"}, 42)
        self.assertTrue(valid)
        self.assertEqual(errors, [])

    def test_invalid_returns_false_with_errors(self):
        valid, errors = validate({"type": "integer"}, "not_int")
        self.assertFalse(valid)
        self.assertGreater(len(errors), 0)


if __name__ == "__main__":
    unittest.main()
