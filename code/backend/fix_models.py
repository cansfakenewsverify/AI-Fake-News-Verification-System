import re
from pathlib import Path

backend_dir = Path("c:/Users/user/OneDrive/桌面/AI-Fake-News-Verification-System/code/backend/factcheck_system/app")

# Fix config.py
config_path = backend_dir / "config.py"
content = config_path.read_text(encoding="utf-8")
content = content.replace('"models/embedding-001"', '"models/text-embedding-004"')
content = content.replace("GEMINI_MODEL: str = \"gemini-2.5-flash\"", "GEMINI_MODEL: str = \"gemini-1.5-flash\"")
config_path.write_text(content, encoding="utf-8")

# Fix ai_service.py
ai_path = backend_dir / "services/ai_service.py"
content = ai_path.read_text(encoding="utf-8")
content = content.replace('["models/gemini-2.5-flash", "gemini-2.5-flash"]', '["gemini-2.5-flash", "gemini-1.5-flash"]')
ai_path.write_text(content, encoding="utf-8")

print("Fixed!")
