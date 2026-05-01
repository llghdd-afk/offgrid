"""
JSON Schema Validator
支持类型验证、$ref引用、oneOf/anyOf组合、嵌套对象和数组验证。

Features:
- Basic type validation (string, number, integer, boolean, null, object, array)
- Required fields check
- Nested object validation with properties
- Array items validation with minItems/maxItems
- $ref references (within same schema using JSON pointer)
- oneOf / anyOf combinators
- minimum/maximum for numbers
- minLength/maxLength for strings
- enum validation
- pattern validation for strings
"""

import re
from typing import Any


class ValidationError:
    """Represents a single validation error."""

    def __init__(self, path: str, message: str):
        self.path = path
        self.message = message

    def __repr__(self):
        return f"ValidationError(path='{self.path}', message='{self.message}')"

    def __eq__(self, other):
        if isinstance(other, ValidationError):
            return self.path == other.path and self.message == other.message
        return False


class SchemaValidator:
    """JSON Schema validator with support for common schema features."""

    def __init__(self, schema: dict):
        self.root_schema = schema
        self.errors: list[ValidationError] = []

    def validate(self, instance: Any) -> bool:
        """Validate an instance against the schema. Returns True if valid."""
        self.errors = []
        self._validate(instance, self.root_schema, "")
        return len(self.errors) == 0

    def _resolve_ref(self, ref: str) -> dict:
        """Resolve a $ref pointer like '#/definitions/Address' within the root schema."""
        if not ref.startswith("#/"):
            raise ValueError(f"Only local refs supported, got: {ref}")

        parts = ref[2:].split("/")
        current = self.root_schema
        for part in parts:
            if isinstance(current, dict) and part in current:
                current = current[part]
            else:
                raise ValueError(f"Cannot resolve ref: {ref}")
        return current

    def _validate(self, instance: Any, schema: dict, path: str) -> None:
        """Core recursive validation logic."""

        # Handle $ref - resolve and validate against referenced schema
        if "$ref" in schema:
            resolved = self._resolve_ref(schema["$ref"])
            self._validate(instance, resolved, path)
            return

        # Handle enum
        if "enum" in schema:
            if instance not in schema["enum"]:
                self.errors.append(ValidationError(
                    path, f"Value {instance!r} not in enum {schema['enum']}"
                ))
                return

        # Handle oneOf
        if "oneOf" in schema:
            match_count = 0
            for sub_schema in schema["oneOf"]:
                sub_validator = SchemaValidator(self.root_schema)
                sub_validator._validate(instance, sub_schema, path)
                if len(sub_validator.errors) == 0:
                    match_count += 1
            if match_count < 1:
                self.errors.append(ValidationError(
                    path, f"Value does not match any schema in oneOf"
                ))
            return

        # Handle anyOf
        if "anyOf" in schema:
            any_valid = False
            for sub_schema in schema["anyOf"]:
                sub_validator = SchemaValidator(self.root_schema)
                sub_validator._validate(instance, sub_schema, path)
                if len(sub_validator.errors) == 0:
                    any_valid = True
                    break
            if not any_valid:
                self.errors.append(ValidationError(
                    path, f"Value does not match any schema in anyOf"
                ))
            return

        # Type validation
        if "type" in schema:
            expected_type = schema["type"]
            if not self._check_type(instance, expected_type):
                self.errors.append(ValidationError(
                    path,
                    f"Expected type '{expected_type}', got '{type(instance).__name__}'"
                ))
                return  # No point validating further if type is wrong

        # String validations
        if isinstance(instance, str):
            if "minLength" in schema and len(instance) < schema["minLength"]:
                self.errors.append(ValidationError(
                    path, f"String length {len(instance)} < minLength {schema['minLength']}"
                ))
            if "maxLength" in schema and len(instance) > schema["maxLength"]:
                self.errors.append(ValidationError(
                    path, f"String length {len(instance)} > maxLength {schema['maxLength']}"
                ))
            if "pattern" in schema:
                if not re.search(schema["pattern"], instance):
                    self.errors.append(ValidationError(
                        path, f"String does not match pattern '{schema['pattern']}'"
                    ))

        # Number validations
        if isinstance(instance, (int, float)) and not isinstance(instance, bool):
            if "minimum" in schema and instance < schema["minimum"]:
                self.errors.append(ValidationError(
                    path, f"Value {instance} < minimum {schema['minimum']}"
                ))
            if "maximum" in schema and instance > schema["maximum"]:
                self.errors.append(ValidationError(
                    path, f"Value {instance} > maximum {schema['maximum']}"
                ))

        # Object validations
        if isinstance(instance, dict):
            self._validate_object(instance, schema, path)

        # Array validations
        if isinstance(instance, list):
            self._validate_array(instance, schema, path)

    def _check_type(self, instance: Any, expected: str) -> bool:
        """Check if instance matches the expected JSON Schema type."""
        type_map = {
            "string": str,
            "boolean": bool,
            "null": type(None),
            "object": dict,
            "array": list,
        }

        if expected == "integer":
            return isinstance(instance, int) and not isinstance(instance, bool)
        elif expected == "number":
            return isinstance(instance, (int, float)) and not isinstance(instance, bool)
        elif expected in type_map:
            if expected == "string":
                return isinstance(instance, str)
            return isinstance(instance, type_map[expected])
        return False

    def _validate_object(self, instance: dict, schema: dict, path: str) -> None:
        """Validate an object instance against object-related schema keywords."""

        # Check required fields
        required = self.root_schema.get("required", [])
        for field in required:
            if field not in instance:
                field_path = f"{path}.{field}" if path else field
                self.errors.append(ValidationError(
                    field_path, f"Required field '{field}' is missing"
                ))

        # Validate properties
        properties = schema.get("properties", {})
        for prop_name, prop_schema in properties.items():
            if prop_name in instance:
                prop_path = f"{path}.{prop_name}" if path else prop_name
                self._validate(instance[prop_name], prop_schema, prop_path)

    def _validate_array(self, instance: list, schema: dict, path: str) -> None:
        """Validate an array instance against array-related schema keywords."""

        # Validate items
        if "items" in schema:
            items_schema = schema["items"]
            for i, item in enumerate(instance):
                item_path = f"{path}[{i}]"
                self._validate(item, items_schema, item_path)

        # Check minItems
        if "minItems" in schema and len(instance) < schema["minItems"]:
            self.errors.append(ValidationError(
                path, f"Array length {len(instance)} < minItems {schema['minItems']}"
            ))

        # Check maxItems
        if "maxItems" in schema and len(instance) >= schema["maxItems"]:
            self.errors.append(ValidationError(
                path, f"Array length {len(instance)} > maxItems {schema['maxItems']}"
            ))


def validate(schema: dict, instance: Any) -> tuple[bool, list[ValidationError]]:
    """Convenience function: validate instance against schema.

    Returns (is_valid, errors) tuple.
    """
    validator = SchemaValidator(schema)
    is_valid = validator.validate(instance)
    return is_valid, validator.errors
