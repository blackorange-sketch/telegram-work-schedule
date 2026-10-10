"""Перевірка без БД: усі функції bot.database, які викликає bot/main.py, імпортовані.

Саме такий пропуск давав помилку 500 при ручній зміні станції
(NameError: set_group_schedule_assignment is not defined).
"""
import ast
import re
import sys

main_src = open("bot/main.py", encoding="utf-8").read()
db_src = open("bot/database.py", encoding="utf-8").read()

db_names = set(re.findall(r"^(?:async )?def (\w+)", db_src, re.M))
tree = ast.parse(main_src)

imported = set()
for node in ast.walk(tree):
    if isinstance(node, ast.ImportFrom):
        imported |= {alias.asname or alias.name for alias in node.names}
    elif isinstance(node, ast.Import):
        imported |= {(alias.asname or alias.name).split(".")[0] for alias in node.names}

defined = {
    node.name for node in ast.walk(tree)
    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
}
used = {
    node.id for node in ast.walk(tree)
    if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load)
}

missing = sorted((used & db_names) - imported - defined)
if missing:
    print("ПОМИЛКА: main.py викликає, але не імпортує:", ", ".join(missing))
    sys.exit(1)
print("ТЕСТ ІМПОРТІВ MAIN.PY ПРОЙДЕНО")
