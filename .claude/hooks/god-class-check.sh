#!/bin/bash
# GOD Class Prevention Hook
# Runs after Edit/Write operations on .py files
# Blocks edits that create GOD classes (>15 methods OR >300 lines per class)

# Get the file path from CLAUDE_FILE_PATHS (space-separated list of edited files)
FILE_PATHS="${CLAUDE_FILE_PATHS:-}"

if [ -z "$FILE_PATHS" ]; then
    exit 0
fi

# GOD class thresholds
MAX_METHODS=15
MAX_LINES=300

# Use Python for accurate class analysis
RESULT=$(python3 << 'PYEOF'
import ast
import sys
import os

file_paths = os.environ.get('CLAUDE_FILE_PATHS', '').split()
max_methods = 15
max_lines = 300
violations = []

for file_path in file_paths:
    # Only check Python files
    if not file_path.endswith('.py'):
        continue

    # Skip if file doesn't exist
    if not os.path.isfile(file_path):
        continue

    # Skip test files
    if '/test' in file_path or '_test.py' in file_path or file_path.startswith('test_'):
        continue

    try:
        with open(file_path, 'r') as f:
            content = f.read()

        tree = ast.parse(content)

        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                # Count methods (including async)
                methods = [n for n in node.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]
                method_count = len(methods)

                # Calculate class line span
                end_line = getattr(node, 'end_lineno', node.lineno)
                line_count = end_line - node.lineno + 1

                class_violations = []
                if method_count > max_methods:
                    class_violations.append(f"{method_count} methods (max: {max_methods})")
                if line_count > max_lines:
                    class_violations.append(f"{line_count} lines (max: {max_lines})")

                if class_violations:
                    violations.append(f"- **{node.name}** in `{file_path}`: {', '.join(class_violations)}")

    except SyntaxError:
        # Skip files with syntax errors
        pass
    except Exception as e:
        # Don't block on unexpected errors
        pass

if violations:
    print("VIOLATION")
    print('\n'.join(violations))
else:
    print("OK")
PYEOF
)

if [[ "$RESULT" == VIOLATION* ]]; then
    echo "## 🚫 GOD Class Violation Detected"
    echo ""
    echo "The following classes exceed GOD class thresholds:"
    echo ""
    echo "$RESULT" | tail -n +2
    echo ""
    echo "### How to Fix"
    echo "1. **Extract services**: Move related methods to focused domain services"
    echo "2. **Use composition**: Delegate to smaller, specialized components"
    echo "3. **Apply SRP**: Each class should have one reason to change"
    echo ""
    exit 1
fi

exit 0
