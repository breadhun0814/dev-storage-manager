"""Extract literal tr() messages to a reviewable UTF-8 gettext template."""
import ast
import json
from pathlib import Path


def main():
    root = Path(__file__).resolve().parents[1]
    messages = {}
    for path in sorted((root / "src/dev_storage_manager").rglob("*.py")):
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "tr" and node.args and isinstance(node.args[0], ast.Constant) and isinstance(node.args[0].value, str):
                messages.setdefault(node.args[0].value, []).append(f"{path.relative_to(root).as_posix()}:{node.lineno}")
    output = root / "docs/locales/messages.pot"
    output.parent.mkdir(parents=True, exist_ok=True)
    lines = ['msgid ""', 'msgstr ""', '"Content-Type: text/plain; charset=UTF-8\\n"', '"Language: ko\\n"', '']
    for message, references in sorted(messages.items()):
        lines.extend(["#: " + " ".join(references), "msgid " + json.dumps(message, ensure_ascii=False), 'msgstr ""', ''])
    output.write_text("\n".join(lines), encoding="utf-8", newline="\n")
    print(f"{len(messages)} messages: {output.relative_to(root)}")


if __name__ == "__main__":
    main()
