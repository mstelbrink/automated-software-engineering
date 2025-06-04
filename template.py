import asyncio
import json
import os
import requests
import subprocess
from dotenv import load_dotenv

load_dotenv()

API_KEY=os.getenv("API_KEY")
BASE_URL="http://188.245.32.59:4000/"
API_URL = "http://localhost:8081/task/index/"
REPOS_DIR = "repos"

async def handle_task(index):
    repo_dir = f"{REPOS_DIR}/repo_{index}"

    response = requests.get(f"{API_URL}{index}")
    task_content = response.json()

    instance_id = task_content["instance_id"]
    issue = task_content["Problem_statement"]
    fail_tests = json.loads(task_content.get("FAIL_TO_PASS", "[]"))
    pass_tests = json.loads(task_content.get("PASS_TO_PASS", "[]"))
    git_clone = task_content["git_clone"].split("&&")
    repo_url = git_clone[0].split()[2]
    commit_hash = git_clone[2].split()[2]

    if not os.path.isdir(repo_dir):
        subprocess.run(["git", "clone", repo_url, repo_dir])
    subprocess.run(["git", "checkout", commit_hash], cwd=repo_dir)

    # Let agent solve issue

    test_payload = {
        "instance_id": instance_id,
        "repoDir": f"/repos/repo_{index}",  # mount with docker
        "FAIL_TO_PASS": fail_tests,
        "PASS_TO_PASS": pass_tests
    }

    # print(test_payload)

    # res = requests.post("http://localhost:8082/test", json=test_payload)
    # res.raise_for_status()
    # print(res.json())



asyncio.run(handle_task(13))