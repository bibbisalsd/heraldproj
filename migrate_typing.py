import os
import re

def process_file(filepath):
    with open(filepath, 'r') as f:
        content = f.read()

    original_content = content

    # Add from __future__ import annotations if not there
    if "from __future__ import annotations" not in content and '"""' in content[:100]:
        parts = content.split('"""')
        if len(parts) >= 3 and content.startswith('"""'):
            content = parts[0] + '"""' + parts[1] + '"""\nfrom __future__ import annotations\n' + '"""'.join(parts[2:])
        else:
            content = "from __future__ import annotations\n" + content
    elif "from __future__ import annotations" not in content:
        content = "from __future__ import annotations\n" + content

    # Replace typing hints for Dict, List, Tuple, Set, Type
    content = re.sub(r'\bDict\[', 'dict[', content)
    content = re.sub(r'\bList\[', 'list[', content)
    content = re.sub(r'\bTuple\[', 'tuple[', content)
    content = re.sub(r'\bSet\[', 'set[', content)
    content = re.sub(r'\bType\[', 'type[', content)
    
    content = re.sub(r':\s*Dict\b', ': dict', content)
    content = re.sub(r':\s*List\b', ': list', content)
    content = re.sub(r':\s*Tuple\b', ': tuple', content)
    content = re.sub(r':\s*Set\b', ': set', content)
    content = re.sub(r':\s*Type\b', ': type', content)
    
    content = re.sub(r'->\s*Dict\b', '-> dict', content)
    content = re.sub(r'->\s*List\b', '-> list', content)
    content = re.sub(r'->\s*Tuple\b', '-> tuple', content)
    content = re.sub(r'->\s*Set\b', '-> set', content)
    content = re.sub(r'->\s*Type\b', '-> type', content)

    # Clean up from typing import ...
    def fix_imports(match):
        imports_str = match.group(1).replace('(', '').replace(')', '')
        imports = imports_str.split(',')
        new_imports = []
        for imp in imports:
            clean_imp = imp.strip()
            if clean_imp not in ('Dict', 'List', 'Tuple', 'Set', 'Type') and clean_imp:
                new_imports.append(clean_imp)
        if not new_imports:
            return ""
        return "from typing import " + ", ".join(new_imports)

    content = re.sub(r'from typing import \(([^)]+)\)', fix_imports, content)
    content = re.sub(r'from typing import ([^\n]+)', fix_imports, content)
    content = re.sub(r'from typing import\s*\n', '\n', content)

    if content != original_content:
        with open(filepath, 'w') as f:
            f.write(content)
        print(f"Updated {filepath}")

def main():
    root = '/home/billybart/Downloads/Harold/esotericv0.2CURRENT/Harold/Jarvis/Jarviscore/jarvis'
    for dirpath, dirnames, filenames in os.walk(root):
        for filename in filenames:
            if filename.endswith(".py"):
                process_file(os.path.join(dirpath, filename))

    test_root = '/home/billybart/Downloads/Harold/esotericv0.2CURRENT/Harold/Jarvis/Jarviscore/tests'
    for dirpath, dirnames, filenames in os.walk(test_root):
        for filename in filenames:
            if filename.endswith(".py"):
                process_file(os.path.join(dirpath, filename))

if __name__ == "__main__":
    main()
