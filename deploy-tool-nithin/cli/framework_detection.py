from pathlib import Path
import json

def detect_framework(project_dir):
    pkg_path = Path(project_dir) / "package.json"
    if not pkg_path.exists():
        return "static"

    with pkg_path.open() as f:
        pkg = json.load(f)
    deps = {**pkg.get('dependencies', {}), **pkg.get('devDependencies', {})}

    if 'react-scripts' in deps or ('react' in deps and 'vite' not in deps and 'next' not in deps):
        return "react"
    if 'vite' in deps:
        return "vite"
    if 'next' in deps:
        return "nextjs"
    return "static"
