import ast
import unittest
from pathlib import Path


class AdminGuardTests(unittest.TestCase):
    def test_every_admin_route_has_an_admin_check(self):
        source = Path('app/handlers/admin.py').read_text(encoding='utf-8')
        tree = ast.parse(source)
        missing = []

        for node in tree.body:
            if not isinstance(node, (ast.AsyncFunctionDef, ast.FunctionDef)):
                continue
            is_route = any(
                isinstance(decorator, ast.Call)
                and isinstance(decorator.func, ast.Attribute)
                and isinstance(decorator.func.value, ast.Name)
                and decorator.func.value.id == 'router'
                for decorator in node.decorator_list
            )
            if not is_route:
                continue
            has_guard = any(
                isinstance(child, ast.Call)
                and isinstance(child.func, ast.Name)
                and child.func.id == 'deny_if_not_admin'
                for child in ast.walk(node)
            )
            if not has_guard:
                missing.append(node.name)

        self.assertEqual(missing, [])


if __name__ == '__main__':
    unittest.main()
