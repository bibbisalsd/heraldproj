import os
for d in ['jarvis', 'tests']:
    for root, _, files in os.walk(d):
        for f in files:
            if f.endswith('.py'):
                path = os.path.join(root, f)
                with open(path, 'r', encoding='utf-8') as file:
                    content = file.read()
                if '\ufeff' in content:
                    content = content.replace('\ufeff', '')
                    with open(path, 'w', encoding='utf-8') as file:
                        file.write(content)
