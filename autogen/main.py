import os
import subprocess
import requests
import asyncio

repos_dir = "repos"
API_URL = "http://localhost:8081/task/index/"

async def handle_task(index):
    response = requests.get(API_URL + str(index))
    testcase = response.json()

asyncio.run(handle_task(1))