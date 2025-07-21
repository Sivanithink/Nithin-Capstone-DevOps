import os
import subprocess
import shutil
import click

def detect_app_type(path):
    if os.path.exists(os.path.join(path, "next.config.js")) or os.path.exists(os.path.join(path, ".next")):
        return "next"
    if os.path.exists(os.path.join(path, "vite.config.js")) or os.path.exists(os.path.join(path, "dist")):
        return "vite"
    if os.path.exists(os.path.join(path, "build")):
        return "react"
    return "static"

def build_project(app_type, path):
    if app_type in ("next", "vite", "react"):
        runner = "yarn" if os.path.exists(os.path.join(path, "yarn.lock")) else "npm"
        install_cmd = [runner, "install"]
        build_cmd = [runner, "run", "build"] if runner == "npm" else [runner, "build"]
        runner_path = shutil.which(runner)
        if runner_path is None:
            click.echo(f"{runner} not found in PATH.")
            exit(1)
        click.echo("Installing dependencies...")
        subprocess.run([runner_path] + install_cmd[1:], check=True)
        click.echo("Building app...")
        subprocess.run([runner_path] + build_cmd[1:], check=True)
        click.echo("Build complete.")
    else:
        click.echo("No build step required for static site.")
