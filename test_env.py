import os
import re

print("Searching for Neo4j terms (case-insensitive) in all files in live_repo:")
patterns = [r"neo4j", r"bolt", r"7687", r"7474", r"netherlands", r"neth", r"vps"]
for root, dirs, files in os.walk("C:\\Agromax\\live_repo"):
    if ".git" in root or "venv" in root:
        continue
    for file in files:
        path = os.path.join(root, file)
        try:
            with open(path, "r", encoding="utf-8", errors="ignore") as f:
                content = f.read()
                for p in patterns:
                    if re.search(p, content, re.IGNORECASE):
                        print(f"Match for '{p}' in: {path}")
                        # Print matching lines
                        f.seek(0)
                        for i, line in enumerate(f):
                            if re.search(p, line, re.IGNORECASE):
                                print(f"  Line {i+1}: {line.strip()}")
        except Exception as e:
            pass
