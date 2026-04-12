"""CodeModifier - LibCST-based Python code modification."""

from __future__ import annotations


import ast
import shutil
from dataclasses import dataclass
from typing import Any

try:
    import libcst as cst
    from libcst import matchers as m  # noqa: F401

    LIBCST_AVAILABLE = True
except ImportError:
    LIBCST_AVAILABLE = False


@dataclass(frozen=True)
class ChangeResult:
    """Result of a code change operation."""

    success: bool
    backup_path: str | None = None
    error: str | None = None
    validation_passed: bool = False
    validation_output: str = ""


SAFE_TARGETS = {
    "jarvis/brain_core/prompt_dispatcher.py",
    "jarvis/brain_core/task_classifier.py",
    "jarvis/brain_core/semantic_command_match.py",
    "jarvis/config.py",
}


class CodeModifier:
    """LibCST-based safe Python code modification.

    Provides structural edits with formatting preservation:
    - add_dict_entry: Add entry to a dictionary literal
    - update_threshold: Update a constant/threshold value
    - add_to_tuple: Add value to a tuple literal
    - add_to_mapping: Add entry to nested dict mapping
    """

    def __init__(self) -> None:
        if not LIBCST_AVAILABLE:
            raise ImportError(
                "libcst is required for CodeModifier. Install with: pip install libcst"
            )

    def _check_safe_target(self, file_path: str) -> None:
        """Raise ValueError if file_path is not in SAFE_TARGETS."""
        # Handle both absolute and relative paths by checking if target is in path
        normalized = str(file_path).replace("\\", "/")
        if not any(target in normalized for target in SAFE_TARGETS):
            raise ValueError(f"Target {file_path} is not in SAFE_TARGETS")

    def add_dict_entry(
        self, file_path: str, dict_name: str, key: str, value: Any
    ) -> ChangeResult:
        """Add an entry to a dictionary literal.

        Args:
            file_path: Path to Python file
            dict_name: Name of the dictionary variable
            key: Key to add
            value: Value for the key

        Returns:
            ChangeResult with success status
        """
        try:
            self._check_safe_target(file_path)
            return self._modify_dict(file_path, dict_name, key, value)
        except Exception as e:
            return ChangeResult(success=False, error=str(e))

    def update_threshold(
        self, file_path: str, var_name: str, new_value: Any
    ) -> ChangeResult:
        """Update a threshold/constant value.

        Args:
            file_path: Path to Python file
            var_name: Name of the variable/threshold
            new_value: New value to set

        Returns:
            ChangeResult with success status
        """
        try:
            self._check_safe_target(file_path)
            with open(file_path) as f:
                source = f.read()

            tree = cst.parse_module(source)
            visitor = ThresholdUpdater(var_name, new_value)
            modified_tree = tree.visit(visitor)

            if not visitor.found:
                return ChangeResult(
                    success=False, error=f"Variable {var_name} not found"
                )

            return self._write_and_validate(file_path, modified_tree.code)
        except Exception as e:
            return ChangeResult(success=False, error=str(e))

    def add_to_tuple(self, file_path: str, tuple_name: str, value: str) -> ChangeResult:
        """Add a value to a tuple literal.

        Args:
            file_path: Path to Python file
            tuple_name: Name of the tuple variable
            value: Value to add

        Returns:
            ChangeResult with success status
        """
        try:
            self._check_safe_target(file_path)
            with open(file_path) as f:
                source = f.read()

            tree = cst.parse_module(source)
            visitor = TupleAdder(tuple_name, value)
            modified_tree = tree.visit(visitor)

            if not visitor.found:
                return ChangeResult(
                    success=False, error=f"Tuple {tuple_name} not found"
                )

            return self._write_and_validate(file_path, modified_tree.code)
        except Exception as e:
            return ChangeResult(success=False, error=str(e))

    def add_to_mapping(
        self,
        file_path: str,
        mapping_name: str,
        outer_key: str,
        inner_key: str,
        value: Any,
    ) -> ChangeResult:
        """Add an entry to a nested dictionary mapping.

        Args:
            file_path: Path to Python file
            mapping_name: Name of the outer dictionary variable
            outer_key: Outer dictionary key
            inner_key: Inner dictionary key to add
            value: Value for the inner key

        Returns:
            ChangeResult with success status
        """
        try:
            self._check_safe_target(file_path)
            return self._modify_nested_dict(
                file_path, mapping_name, outer_key, inner_key, value
            )
        except Exception as e:
            return ChangeResult(success=False, error=str(e))

    def _modify_dict(
        self, file_path: str, dict_name: str, key: str, value: Any
    ) -> ChangeResult:
        """Add entry to dictionary."""
        with open(file_path) as f:
            source = f.read()

        tree = cst.parse_module(source)
        visitor = DictAdder(dict_name, key, value)
        modified_tree = tree.visit(visitor)

        if not visitor.found:
            return ChangeResult(
                success=False, error=f"Dictionary {dict_name} not found"
            )

        return self._write_and_validate(file_path, modified_tree.code)

    def _modify_nested_dict(
        self,
        file_path: str,
        mapping_name: str,
        outer_key: str,
        inner_key: str,
        value: Any,
    ) -> ChangeResult:
        """Add entry to nested dictionary."""
        with open(file_path) as f:
            source = f.read()

        tree = cst.parse_module(source)
        visitor = NestedDictAdder(mapping_name, outer_key, inner_key, value)
        modified_tree = tree.visit(visitor)

        if not visitor.found:
            return ChangeResult(
                success=False, error=f"Mapping {mapping_name} not found"
            )

        return self._write_and_validate(file_path, modified_tree.code)

    def _write_and_validate(self, file_path: str, new_code: str) -> ChangeResult:
        """Write code and validate syntax."""
        # Validate syntax before writing
        try:
            ast.parse(new_code)
        except SyntaxError as e:
            return ChangeResult(
                success=False,
                error=f"Syntax error in generated code: {e}",
            )

        # Create backup
        backup_path = str(file_path) + ".bak"
        shutil.copy2(file_path, backup_path)

        # Write new code
        with open(file_path, "w") as f:
            f.write(new_code)

        return ChangeResult(
            success=True,
            backup_path=backup_path,
            validation_passed=True,
        )


if LIBCST_AVAILABLE:

    class DictAdder(cst.CSTTransformer):
        """Add entry to a dictionary."""

        def __init__(self, dict_name: str, key: str, value: Any) -> None:
            self.dict_name = dict_name
            self.key = key
            self.value = value
            self.found = False

        def leave_Assign(self, original: cst.Assign, updated: cst.Assign) -> cst.Assign:
            if not isinstance(updated.target, cst.Name):
                return updated
            if updated.target.value != self.dict_name:
                return updated

            self.found = True

            if not isinstance(updated.value, cst.Dict):
                return updated

            # Add new element
            new_element = cst.DictElement(
                key=cst.SimpleString(value=f'"{self.key}"'),
                value=self._to_cst_value(self.value),
            )
            new_elements = list(updated.value.elements) + [new_element]

            return updated.with_changes(
                value=updated.value.with_changes(elements=new_elements)
            )

        def _to_cst_value(self, value: Any) -> cst.BaseExpression:
            """Convert Python value to LibCST value."""
            if isinstance(value, str):
                return cst.SimpleString(value=f'"{value}"')
            elif isinstance(value, bool):
                return cst.Name(value="True" if value else "False")
            elif isinstance(value, (int, float)):
                return (
                    cst.Float(value=str(value))
                    if isinstance(value, float)
                    else cst.Integer(value=str(value))
                )
            elif isinstance(value, list):
                elements = [cst.Element(self._to_cst_value(v)) for v in value]
                return cst.List(elements=elements)
            else:
                return cst.SimpleString(value=f'"{value}"')

    class NestedDictAdder(cst.CSTTransformer):
        """Add entry to nested dictionary."""

        def __init__(
            self, mapping_name: str, outer_key: str, inner_key: str, value: Any
        ) -> None:
            self.mapping_name = mapping_name
            self.outer_key = outer_key
            self.inner_key = inner_key
            self.value = value
            self.found = False
            self._in_outer_dict = False
            self._outer_key_found = False

        def leave_Assign(self, original: cst.Assign, updated: cst.Assign) -> cst.Assign:
            if not isinstance(updated.target, cst.Name):
                return updated
            if updated.target.value != self.mapping_name:
                return updated

            self.found = True

            if not isinstance(updated.value, cst.Dict):
                return updated

            # Find outer key and add inner key
            new_elements = []
            for element in updated.value.elements:
                new_elements.append(element)
                if isinstance(element, cst.DictElement):
                    key_str = self._get_string_value(element.key)
                    if key_str == self.outer_key:
                        # Add inner key to this dict
                        if isinstance(element.value, cst.Dict):
                            new_inner = cst.DictElement(
                                key=cst.SimpleString(value=f'"{self.inner_key}"'),
                                value=self._to_cst_value(self.value),
                            )
                            new_value = cst.Dict(
                                elements=list(element.value.elements) + [new_inner]
                            )
                            new_elements[-1] = element.with_changes(value=new_value)

            return updated.with_changes(
                value=updated.value.with_changes(elements=new_elements)
            )

        def _get_string_value(self, node: cst.BaseExpression) -> str:
            """Extract string value from CST node."""
            if isinstance(node, cst.SimpleString):
                return node.value.strip("\"'")
            return ""

        def _to_cst_value(self, value: Any) -> cst.BaseExpression:
            """Convert Python value to LibCST value."""
            if isinstance(value, str):
                return cst.SimpleString(value=f'"{value}"')
            elif isinstance(value, bool):
                return cst.Name(value="True" if value else "False")
            elif isinstance(value, (int, float)):
                return (
                    cst.Float(value=str(value))
                    if isinstance(value, float)
                    else cst.Integer(value=str(value))
                )
            else:
                return cst.SimpleString(value=f'"{value}"')

    class ThresholdUpdater(cst.CSTTransformer):
        """Update a threshold/constant value."""

        def __init__(self, var_name: str, new_value: Any) -> None:
            self.var_name = var_name
            self.new_value = new_value
            self.found = False

        def leave_Assign(self, original: cst.Assign, updated: cst.Assign) -> cst.Assign:
            if not isinstance(updated.target, cst.Name):
                return updated
            if updated.target.value != self.var_name:
                return updated

            self.found = True
            return updated.with_changes(value=self._to_cst_value(self.new_value))

        def _to_cst_value(self, value: Any) -> cst.BaseExpression:
            """Convert Python value to LibCST value."""
            if isinstance(value, str):
                return cst.SimpleString(value=f'"{value}"')
            elif isinstance(value, bool):
                return cst.Name(value="True" if value else "False")
            elif isinstance(value, float):
                return cst.Float(value=str(value))
            elif isinstance(value, int):
                return cst.Integer(value=str(value))
            else:
                return cst.SimpleString(value=f'"{value}"')

    class TupleAdder(cst.CSTTransformer):
        """Add value to a tuple."""

        def __init__(self, tuple_name: str, value: str) -> None:
            self.tuple_name = tuple_name
            self.value = value
            self.found = False

        def leave_Assign(self, original: cst.Assign, updated: cst.Assign) -> cst.Assign:
            if not isinstance(updated.target, cst.Name):
                return updated
            if updated.target.value != self.tuple_name:
                return updated

            self.found = True

            if not isinstance(updated.value, cst.Tuple):
                return updated

            new_element = cst.Element(cst.SimpleString(value=f'"{self.value}"'))
            new_elements = list(updated.value.elements) + [new_element]

            return updated.with_changes(
                value=updated.value.with_changes(elements=new_elements)
            )
