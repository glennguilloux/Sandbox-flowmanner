#!/usr/bin/env python3
"""Debug script: exercise convert_logger_kwargs on a minimal test case to reveal the splice bug.

Usage: python3 scripts/debug_converter_splice.py
"""
import sys
sys.path.insert(0, "scripts")
from convert_logger_kwargs import transform_source

# Test case 1: single-line call inside except block
src1 = '''def foo():
    try:
        x = 1
    except Exception as e:
        logger.debug("event", error=str(e))
    return x
'''

# Test case 2: multi-line call inside except block
src2 = '''def foo():
    try:
        x = 1
    except Exception:
        logger.debug(
            "dual_write_sync_run_status_failed", mission_id=mid, exc_info=True
        )
    return x
'''

# Test case 3: call at module level (no enclosing except)
src3 = '''logger.debug("event", error=str(e))
'''

# Test case 4: call in a method inside a class inside an except
src4 = '''class Foo:
    def bar(self):
        try:
            x = 1
        except Exception as e:
            self.logger.debug("event", error=str(e))
        return x
'''

for i, src in enumerate([src1, src2, src3, src4], 1):
    print(f"=== Test case {i} ===")
    print("--- INPUT ---")
    print(src)
    new_src, converted, skipped = transform_source(src)
    print(f"--- OUTPUT (converted={converted}, skipped={skipped}) ---")
    print(new_src)
    # Verify it parses
    import ast
    try:
        ast.parse(new_src)
        print("--- PARSE: OK ---")
    except SyntaxError as e:
        print(f"--- PARSE: FAILED on line {e.lineno}: {e.msg} ---")
    print()
