from pathlib import Path

def write_dockerfile(project_dir, framework):
    dockerfile_path = Path(project_dir) / "Dockerfile"

    # 💡 All builds are performed locally, Docker just serves static files
    content = '''
    FROM nginx:alpine
    COPY . /usr/share/nginx/html
    EXPOSE 80
    CMD ["nginx", "-g", "daemon off;"]
    '''

    dockerfile_path.write_text(content.strip() + "\n")
