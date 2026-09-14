import ast
import contextlib
import io
import sys
from pathlib import Path

EXCLUDED_DIRS = {
    ".agents",
    ".git",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".scratch",
    ".venv",
    "__pycache__",
    "build",
    "dist",
    "node_modules",
    "venv",
}


def is_docstring(stmt: ast.AST) -> bool:
    """Проверяет, является ли узел синтаксического дерева строковой константой (докстрингом)."""
    return (
        isinstance(stmt, ast.Expr)
        and isinstance(stmt.value, ast.Constant)
        and isinstance(stmt.value.value, str)
    )


class SkeletonTransformer(ast.NodeTransformer):
    """Трансформер AST, сохраняющий только импорты, объявления классов,

    сигнатуры функций/методов с type hints и докстринги.
    Тела всех функций и методов заменяются на ast.Ellipsis (...).
    """

    def visit_Module(self, node: ast.Module) -> ast.Module:
        new_body: list[ast.stmt] = []
        if node.body and is_docstring(node.body[0]):
            new_body.append(node.body[0])
            stmts = node.body[1:]
        else:
            stmts = node.body

        for stmt in stmts:
            if isinstance(stmt, (ast.Import, ast.ImportFrom)):
                new_body.append(stmt)
            elif isinstance(
                stmt, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)
            ):
                transformed = self.visit(stmt)
                if transformed is not None:
                    new_body.append(transformed)

        node.body = new_body
        return node

    def visit_ClassDef(self, node: ast.ClassDef) -> ast.ClassDef:
        new_body: list[ast.stmt] = []
        if node.body and is_docstring(node.body[0]):
            new_body.append(node.body[0])
            stmts = node.body[1:]
        else:
            stmts = node.body

        for stmt in stmts:
            if isinstance(stmt, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
                transformed = self.visit(stmt)
                if transformed is not None:
                    new_body.append(transformed)

        if not new_body:
            new_body = [ast.Expr(value=ast.Constant(value=Ellipsis))]

        node.body = new_body
        return node

    def visit_FunctionDef(self, node: ast.FunctionDef) -> ast.FunctionDef:
        return self._transform_function(node)

    def visit_AsyncFunctionDef(
        self, node: ast.AsyncFunctionDef
    ) -> ast.AsyncFunctionDef:
        return self._transform_function(node)

    def _transform_function(
        self, node: ast.FunctionDef | ast.AsyncFunctionDef
    ) -> ast.FunctionDef | ast.AsyncFunctionDef:
        ellipsis_expr = ast.Expr(value=ast.Constant(value=Ellipsis))
        if node.body and is_docstring(node.body[0]):
            node.body = [node.body[0], ellipsis_expr]
        else:
            node.body = [ellipsis_expr]
        return node


def extract_skeleton(source_code: str, filename: str = "<string>") -> str:
    """Парсит синтаксическое дерево и возвращает скелет исходного кода."""
    tree = ast.parse(source_code, filename=filename)
    transformer = SkeletonTransformer()
    transformed_tree = transformer.visit(tree)
    ast.fix_missing_locations(transformed_tree)
    return ast.unparse(transformed_tree)


def should_skip(path: Path) -> bool:
    """Проверяет, находится ли путь в исключаемых служебных директориях."""
    return any(part in EXCLUDED_DIRS for part in path.parts)


def find_files(target: Path) -> list[Path]:
    """Находит Python-файлы: по файлу, директории или поиску по имени файла."""
    if target.is_file():
        return [target]

    if target.is_dir():
        return [path for path in target.rglob("*.py") if not should_skip(path)]

    # Если путь не найден напрямую (например, передан service.py без пути)
    return [path for path in Path.cwd().rglob(target.name) if not should_skip(path)]


def main() -> None:
    if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
        with contextlib.suppress(AttributeError, io.UnsupportedOperation):
            sys.stdout.reconfigure(encoding="utf-8")

    raw_target = sys.argv[1] if len(sys.argv) > 1 else "."
    target = Path(raw_target)

    files = find_files(target)

    if not files:
        print(f"Ошибка: Python-файлы не найдены для: {target}", file=sys.stderr)
        sys.exit(1)

    sorted_files = sorted(files)
    is_multi = len(sorted_files) > 1 or target.is_dir()

    for file_path in sorted_files:
        try:
            rel_path = file_path.relative_to(Path.cwd())
        except ValueError:
            rel_path = file_path

        if is_multi:
            print(f"\n{'=' * 80}")
            print(f"FILE: {rel_path}")
            print(f"{'=' * 80}\n")

        try:
            source_code = file_path.read_text(encoding="utf-8")
            skeleton = extract_skeleton(source_code, filename=str(file_path))
            print(skeleton)
        except (SyntaxError, UnicodeDecodeError) as exc:
            print(f"[ОШИБКА в {rel_path}] {exc}", file=sys.stderr)


if __name__ == "__main__":
    main()
