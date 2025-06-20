import asyncio
import json
import os
import requests
import subprocess
from praisonaiagents import Agent, Agents, MCP
from dotenv import load_dotenv
from prompts import planner_prompt, coder_prompt, tester_prompt

load_dotenv()

API_KEY=os.getenv("API_KEY")
BASE_URL=os.getenv("BASE_URL")
API_URL = "http://localhost:8081/task/index/"
TEST_URL = "http://localhost:8082/test"
REPOS_DIR = "repos"
LOG_FILE = "results_praisonai.log"

llm_config = {
    "model": "gpt-4o",
    "temperature": 0,
    "max_tokens": 4096,
    "api_key": API_KEY,
    "base_url": BASE_URL,
}

async def handle_task(index):

    repo_dir = f"{REPOS_DIR}/repo_{index}"
    start_dir = os.getcwd()

    try:
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

        allowed_dir = os.getcwd() + "/repos"
        allowed_dirs = [
            allowed_dir
        ]

        tools = MCP("npx -y @modelcontextprotocol/server-filesystem", args=allowed_dirs)

        planner = Agent(
            instructions=planner_prompt,
            llm=llm_config
        )

        coder = Agent(
            instructions=coder_prompt,
            llm=llm_config,
            tools=tools
        )

        tester = Agent(
            instructions=tester_prompt,
            llm=llm_config,
            tools=tools
        )

        agents = Agents(agen=[planner, coder, tester])

        full_prompt = (
                f"Work in the directory: {allowed_dir}/repo_{index}. This is a Git repository.\n"
                f"Your goal is to fix the problem described below.\n"
                f"All code changes must be saved to the files, so they appear in `git diff`.\n"
                f"Problem description:\n"
                f"{issue}\n\n"
                f"Make sure the fix is minimal and only touches what's necessary to resolve the failing tests."
            )

        agents.start(task_content=full_prompt)

        test_payload = {
            "instance_id": instance_id,
            "repoDir": f"/repos/repo_{index}",
            "FAIL_TO_PASS": fail_tests,
            "PASS_TO_PASS": pass_tests
        }

        res = requests.post(TEST_URL, json=test_payload)
        res.raise_for_status()
        result_raw = res.json().get("harnessOutput", "{}")
        result_json = json.loads(result_raw)
        if not result_json:
            raise ValueError("No data in harnessOutput – possible evaluation error or empty result")
        instance_id = next(iter(result_json))
        tests_status = result_json[instance_id]["tests_status"]
        fail_pass_results = tests_status["FAIL_TO_PASS"]
        fail_pass_total = len(fail_pass_results["success"]) + len(fail_pass_results["failure"])
        fail_pass_passed = len(fail_pass_results["success"])
        pass_pass_results = tests_status["PASS_TO_PASS"]
        pass_pass_total = len(pass_pass_results["success"]) + len(pass_pass_results["failure"])
        pass_pass_passed = len(pass_pass_results["success"])

        # Log results
        os.chdir(start_dir)
        with open(LOG_FILE, "a", encoding="utf-8") as log:
            log.write(f"\n--- TESTCASE {index} ---\n")
            log.write(f"FAIL_TO_PASS passed: {fail_pass_passed}/{fail_pass_total}\n")
            log.write(f"PASS_TO_PASS passed: {pass_pass_passed}/{pass_pass_total}\n")
        print(f"Test case {index} completed and logged.")

    except Exception as e:
        os.chdir(start_dir)
        with open(LOG_FILE, "a", encoding="utf-8") as log:
            log.write(f"\n--- TESTCASE {index} ---\n")
            log.write(f"Error: {e}\n")
        print(f"Error in test case {index}: {e}")

async def main():
    for i in range(1, 301):
        await handle_task(i)


if __name__ == "__main__":
    asyncio.run(main())