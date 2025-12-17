import sys
import os

path = "venv/lib/python3.9/site-packages/google/api_core/_python_version_support.py"

with open(path, "r") as f:
    content = f.read()

# The target block to replace
target = """else:
    from importlib import metadata

    def _get_pypi_package_name(module_name):"""

replacement = """else:
    import sys
    if sys.version_info < (3, 10):
        try:
            import importlib_metadata as metadata
        except ImportError:
            from importlib import metadata
    else:
        from importlib import metadata

    def _get_pypi_package_name(module_name):"""

if target in content:
    new_content = content.replace(target, replacement)
    with open(path, "w") as f:
        f.write(new_content)
    print("Patched successfully.")
else:
    print("Target not found.")
