"""
ClickUp v2 API client.
Creates tasks in the correct list based on department.
"""

import requests
from loguru import logger
from core.models import ClickUpTask, Department
from config.settings import get_settings

BASE_URL = "https://api.clickup.com/api/v2"


class ClickUpClient:

    def __init__(self):
        s = get_settings()
        self.headers = {
            "Authorization": s.clickup_api_token,
            "Content-Type": "application/json",
        }
        self.list_ids = {
            Department.DEVELOPERS: s.clickup_list_developers,
            Department.SALES: s.clickup_list_sales,
            Department.OTHER: s.clickup_list_other,
        }

    def verify_connection(self) -> bool:
        try:
            r = requests.get(f"{BASE_URL}/user", headers=self.headers, timeout=10)
            r.raise_for_status()
            username = r.json().get("user", {}).get("username", "unknown")
            logger.info(f"ClickUp connected as: {username}")
            return True
        except Exception as e:
            logger.error(f"ClickUp connection failed: {e}")
            return False

    def create_task(self, task: ClickUpTask) -> str | None:
        list_id = self.list_ids.get(task.department, self.list_ids[Department.OTHER])

        description = task.description
        if task.source_post_url:
            description += f"\n\n---\nSource: {task.source_post_url}"

        payload = {
            "name": task.name,
            "description": description,
            "priority": task.priority,
            "tags": task.tags,
        }

        try:
            r = requests.post(
                f"{BASE_URL}/list/{list_id}/task",
                headers=self.headers,
                json=payload,
                timeout=15,
            )
            r.raise_for_status()
            task_id = r.json().get("id")
            logger.info(f"ClickUp task created: '{task.name}' → {task_id} (list {list_id})")
            return task_id
        except requests.HTTPError as e:
            logger.error(f"ClickUp HTTP error {e.response.status_code}: {e.response.text}")
            return None
        except Exception as e:
            logger.error(f"ClickUp request error: {e}")
            return None

    def create_tasks_batch(self, tasks: list[ClickUpTask]) -> list[str]:
        ids = []
        for task in tasks:
            task_id = self.create_task(task)
            if task_id:
                ids.append(task_id)
        return ids
