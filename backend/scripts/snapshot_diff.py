#!/usr/bin/env python3
"""Diff SQLAlchemy metadata snapshots produced by snapshot_model_metadata.py."""

from __future__ import annotations

import json
import os
import sys
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence

_IGNORED_TOP_LEVEL_KEYS = {"alembic_version", "generated_at", "model_count"}
_ALLOWED_TOP_LEVEL_KEYS = _IGNORED_TOP_LEVEL_KEYS | {"tables"}
_REQUIRED_TABLE_KEYS = {"columns", "foreign_keys", "indexes", "name", "unique_constraints"}


def _validate_snapshot(snapshot: object, label: str) -> dict[str, object]:
    if not isinstance(snapshot, dict):
        raise ValueError(f"{label} snapshot must be a dictionary")

    unexpected_keys = sorted(set(snapshot) - _ALLOWED_TOP_LEVEL_KEYS)
    if unexpected_keys:
        joined_keys = ", ".join(unexpected_keys)
        raise ValueError(f"{label} snapshot has unexpected top-level keys: {joined_keys}")

    if not isinstance(snapshot.get("tables"), list):
        raise ValueError(f"{label} snapshot must contain a tables list")

    return snapshot


def _seen_key(item: object) -> tuple[str, str]:
    return (type(item).__name__, repr(item))


def _validate_unique(items: Sequence[object], path: str, label: str) -> None:
    seen: set[tuple[str, str]] = set()
    for item in items:
        item_key = _seen_key(item)
        if item_key in seen:
            raise ValueError(f"{label} snapshot {path} contains duplicate entries: {item!r}")
        seen.add(item_key)


def _validate_string_list(value: object, path: str, label: str) -> list[str]:
    if not isinstance(value, list):
        raise ValueError(f"{label} snapshot {path} must be a list of strings")

    string_list = []
    for item in value:
        if not isinstance(item, str):
            raise ValueError(f"{label} snapshot {path} must be a list of strings")
        string_list.append(item)

    _validate_unique(string_list, path, label)
    return string_list


def _validate_string_list_list(value: object, path: str, label: str) -> list[list[str]]:
    if not isinstance(value, list):
        raise ValueError(f"{label} snapshot {path} must be a list of string lists")

    nested_lists = []
    for index, item in enumerate(value):
        item_path = f"{path}[{index}]"
        if not isinstance(item, list):
            raise ValueError(f"{label} snapshot {item_path} must be a list of strings")

        string_list = []
        for nested_item in item:
            if not isinstance(nested_item, str):
                raise ValueError(f"{label} snapshot {item_path} must be a list of strings")
            string_list.append(nested_item)

        _validate_unique(string_list, item_path, label)
        nested_lists.append(string_list)

    _validate_unique(nested_lists, path, label)
    return nested_lists


def _validate_string_pair_list(value: object, path: str, label: str) -> list[list[str]]:
    if not isinstance(value, list):
        raise ValueError(f"{label} snapshot {path} must be a list of [source, target] pairs")

    pairs = []
    for index, item in enumerate(value):
        item_path = f"{path}[{index}]"
        if not isinstance(item, list) or len(item) != 2:
            raise ValueError(f"{label} snapshot {item_path} must be a [source, target] pair")

        source, target = item
        if not isinstance(source, str) or not isinstance(target, str):
            raise ValueError(f"{label} snapshot {item_path} must be a [source, target] pair")

        pair = [source, target]
        pairs.append(pair)

    _validate_unique(pairs, path, label)
    return pairs


def _validate_table(table: object, label: str, path: str) -> dict[str, object]:
    if not isinstance(table, dict):
        raise ValueError(f"{label} snapshot {path} must be a table dictionary")

    missing_keys = sorted(_REQUIRED_TABLE_KEYS - set(table))
    if missing_keys:
        joined_keys = ", ".join(missing_keys)
        raise ValueError(f"{label} snapshot {path} is missing required keys: {joined_keys}")

    unexpected_keys = sorted(set(table) - _REQUIRED_TABLE_KEYS)
    if unexpected_keys:
        joined_keys = ", ".join(unexpected_keys)
        raise ValueError(f"{label} snapshot {path} has unexpected keys: {joined_keys}")

    name = table["name"]
    if not isinstance(name, str) or not name:
        raise ValueError(f"{label} snapshot {path}.name must be a non-empty string")

    columns = table["columns"]
    if not isinstance(columns, dict):
        raise ValueError(f"{label} snapshot {path}.columns must be a column type dictionary")

    for column_name, column_type in columns.items():
        if not isinstance(column_name, str) or not isinstance(column_type, str):
            raise ValueError(f"{label} snapshot {path}.columns must map column names to string types")

    _validate_string_list(table["indexes"], f"{path}.indexes", label)
    _validate_string_list_list(table["unique_constraints"], f"{path}.unique_constraints", label)
    _validate_string_pair_list(table["foreign_keys"], f"{path}.foreign_keys", label)

    return table


def _table_map(snapshot: dict[str, object], label: str) -> dict[str, dict[str, object]]:
    tables = snapshot["tables"]
    table_map: dict[str, dict[str, object]] = {}

    for index, table in enumerate(tables):
        validated_table = _validate_table(table, label, f"tables[{index}]")
        name = str(validated_table["name"])
        if name in table_map:
            raise ValueError(f"{label} snapshot contains duplicate table names: {name}")
        table_map[name] = validated_table

    return table_map


def _unique_constraint_labels(table: Mapping[str, object]) -> set[str]:
    return {json.dumps(columns, sort_keys=True) for columns in table["unique_constraints"]}


def _foreign_key_labels(table: Mapping[str, object]) -> set[str]:
    return {json.dumps(foreign_key, sort_keys=True) for foreign_key in table["foreign_keys"]}


def _cap_lines(lines: list[str]) -> list[str]:
    if len(lines) <= 50:
        return lines

    hidden_count = len(lines) - 49
    return [*lines[:49], f"... and {hidden_count} more"]


def diff_snapshots(old: dict, new: dict) -> list[str]:
    old_snapshot = _validate_snapshot(old, "old")
    new_snapshot = _validate_snapshot(new, "new")
    old_tables = _table_map(old_snapshot, "old")
    new_tables = _table_map(new_snapshot, "new")

    old_names = set(old_tables)
    new_names = set(new_tables)
    lines: list[str] = []

    lines.extend([f"+ tables.{table_name} (added)" for table_name in sorted(new_names - old_names)])
    lines.extend([f"- tables.{table_name} (removed)" for table_name in sorted(old_names - new_names)])

    for table_name in sorted(old_names & new_names):
        old_table = old_tables[table_name]
        new_table = new_tables[table_name]
        old_columns = old_table["columns"]
        new_columns = new_table["columns"]

        old_column_names = set(old_columns)
        new_column_names = set(new_columns)

        lines.extend(
            [
                f"+ tables.{table_name}.columns.{column_name} = {new_columns[column_name]} (added)"
                for column_name in sorted(new_column_names - old_column_names)
            ]
        )

        lines.extend(
            [
                f"- tables.{table_name}.columns.{column_name} (removed)"
                for column_name in sorted(old_column_names - new_column_names)
            ]
        )

        lines.extend(
            [
                f"~ tables.{table_name}.columns.{column_name}: {old_columns[column_name]} -> {new_columns[column_name]}"
                for column_name in sorted(old_column_names & new_column_names)
                if old_columns[column_name] != new_columns[column_name]
            ]
        )

        old_indexes = set(old_table["indexes"])
        new_indexes = set(new_table["indexes"])
        lines.extend(
            [
                f"+ tables.{table_name}.indexes.{index_name} (added)"
                for index_name in sorted(new_indexes - old_indexes)
            ]
        )
        lines.extend(
            [
                f"- tables.{table_name}.indexes.{index_name} (removed)"
                for index_name in sorted(old_indexes - new_indexes)
            ]
        )

        old_unique_constraints = _unique_constraint_labels(old_table)
        new_unique_constraints = _unique_constraint_labels(new_table)
        lines.extend(
            [
                f"+ tables.{table_name}.unique_constraints.{unique_constraint} (added)"
                for unique_constraint in sorted(new_unique_constraints - old_unique_constraints)
            ]
        )
        lines.extend(
            [
                f"- tables.{table_name}.unique_constraints.{unique_constraint} (removed)"
                for unique_constraint in sorted(old_unique_constraints - new_unique_constraints)
            ]
        )

        old_foreign_keys = _foreign_key_labels(old_table)
        new_foreign_keys = _foreign_key_labels(new_table)
        lines.extend(
            [
                f"+ tables.{table_name}.foreign_keys.{foreign_key} (added)"
                for foreign_key in sorted(new_foreign_keys - old_foreign_keys)
            ]
        )
        lines.extend(
            [
                f"- tables.{table_name}.foreign_keys.{foreign_key} (removed)"
                for foreign_key in sorted(old_foreign_keys - new_foreign_keys)
            ]
        )

    return _cap_lines(lines)


def _load_json(path: str) -> dict:
    with open(path, encoding="utf-8") as snapshot_file:
        loaded_snapshot = json.load(snapshot_file)

    if not isinstance(loaded_snapshot, dict):
        raise ValueError(f"{path} must contain a JSON object")

    return loaded_snapshot


def _resolve_paths(argv: list[str]) -> tuple[str, str]:
    if len(argv) == 2:
        old_path, new_path = argv
    elif len(argv) == 0:
        old_path = os.environ.get("OLD_SNAPSHOT", "")
        new_path = os.environ.get("NEW_SNAPSHOT", "")
    else:
        raise SystemExit("usage: snapshot_diff.py [old_path new_path]")

    if not old_path or not new_path:
        raise SystemExit("usage: snapshot_diff.py [old_path new_path] or set OLD_SNAPSHOT and NEW_SNAPSHOT")

    return old_path, new_path


def main(argv: list[str] | None = None) -> int:
    if argv is None:
        argv = sys.argv[1:]

    try:
        old_path, new_path = _resolve_paths(argv)
        diff_lines = diff_snapshots(_load_json(old_path), _load_json(new_path))
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        print(f"snapshot diff error: {exc}", file=sys.stderr)
        return 2

    for line in diff_lines:
        print(line)

    return 1 if diff_lines else 0


if __name__ == "__main__":
    raise SystemExit(main())
