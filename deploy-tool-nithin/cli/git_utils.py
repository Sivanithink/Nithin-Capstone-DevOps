# cli/git_utils.py
import git

def clone_repo(url):
    repo_dir = url.split('/')[-1].replace('.git', '')
    git.Repo.clone_from(url, repo_dir)
    return repo_dir
