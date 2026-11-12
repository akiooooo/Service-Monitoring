"""собираем исходники для проверки без окружения, базы и истории Git"""
import hashlib
import json
import re
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main():
    files = [ROOT / name for name in ("README.md", "Task.txt", "CONTRIBUTING.md",
             "run.py", "Dockerfile", "compose.yaml", ".gitignore", ".gitattributes", ".dockerignore")]
    for folder in ("monitor", "scripts", "tests", "docs", ".github"):
        files.extend(p for p in (ROOT / folder).rglob("*")
                     if p.is_file() and "__pycache__" not in p.parts)
    files.append(ROOT / "data" / ".gitkeep")
    files = sorted(set(files))
    secret = re.compile(rb"\b\d{6,14}:[A-Za-z0-9_-]{30,}\b|\bgh[pousr]_[A-Za-z0-9]{30,}\b|-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----")
    content = {}
    for path in files:
        name = path.relative_to(ROOT).as_posix()
        if not path.is_file():
            raise SystemExit(f"Нет обязательного файла: {name}")
        if path.suffix in (".db", ".sqlite3", ".log", ".pyc", ".zip") or path.name.startswith(".env"):
            raise SystemExit(f"Лишний файл: {name}")
        data = path.read_bytes()
        if secret.search(data):
            raise SystemExit(f"Проверьте возможный секрет в {name}, значение скрыто")
        content[name] = data
    manifest = {name: hashlib.sha256(data).hexdigest() for name, data in content.items()}
    output = ROOT / "dist" / "Pulse-for-review.zip"
    output.parent.mkdir(exist_ok=True)
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, data in content.items():
            archive.writestr("Pulse/" + name, data)
        archive.writestr("Pulse/MANIFEST.json", json.dumps(manifest, ensure_ascii=False, indent=2))
    print(f"{output}: {len(content)} files + SHA-256 manifest")


if __name__ == "__main__":
    main()
