import os
import json
import time
from typing import List, Dict, Any, Optional
from playwright.sync_api import sync_playwright


class TestDataManager:
    __test__ = False

    def __init__(self, workspace_dir: str):
        self.workspace_dir = workspace_dir
        self.data_dir = os.path.join(workspace_dir, "test_data")
        self.envs_file = os.path.join(self.data_dir, "environments.json")
        self._ensure_storage()

    def _ensure_storage(self):
        os.makedirs(self.data_dir, exist_ok=True)
        if not os.path.exists(self.envs_file):
            default_meta = {
                "active_env": "QA",
                "environments": ["QA", "Staging", "Prod"]
            }
            with open(self.envs_file, "w", encoding="utf-8") as f:
                json.dump(default_meta, f, indent=2)

        for env_name in ["QA", "Staging", "Prod"]:
            env_file = os.path.join(self.data_dir, f"{env_name}.json")
            if not os.path.exists(env_file):
                self._seed_env_file(env_name, env_file)

    def _seed_env_file(self, env_name: str, file_path: str):
        subdomain = env_name.lower()
        seed_data = {
            "environment": env_name,
            "last_updated": time.time(),
            "variables": {
                "base_url": f"https://demo.playwright.dev/todomvc/",
                "api_endpoint": f"https://api.{subdomain}.conduit.io/v1",
                "username": f"{subdomain}_user@conduit.io",
                "password": f"{subdomain}_pass_2026",
                "timeout": 5000,
                "retry_count": 2 if env_name != "Prod" else 1
            },
            "datasets": {
                "users": [
                    {"id": 1, "username": f"admin@{subdomain}.io", "role": "admin", "status": "active"},
                    {"id": 2, "username": f"qa@{subdomain}.io", "role": "qa_tester", "status": "active"},
                    {"id": 3, "username": f"guest@{subdomain}.io", "role": "viewer", "status": "inactive"}
                ],
                "todo_items": [
                    {"title": f"Review {env_name} deployment", "completed": False},
                    {"title": f"Verify {env_name} smoke tests", "completed": True},
                    {"title": f"Generate QA test report for {env_name}", "completed": False}
                ]
            }
        }
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(seed_data, f, indent=2)

    def get_environments(self) -> List[str]:
        if os.path.exists(self.envs_file):
            try:
                with open(self.envs_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    return data.get("environments", ["QA", "Staging", "Prod"])
            except Exception:
                pass
        return ["QA", "Staging", "Prod"]

    def get_active_environment(self) -> str:
        if os.path.exists(self.envs_file):
            try:
                with open(self.envs_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    return data.get("active_env", "QA")
            except Exception:
                pass
        return "QA"

    def set_active_environment(self, env_name: str):
        envs = self.get_environments()
        if env_name not in envs:
            envs.append(env_name)
        data = {
            "active_env": env_name,
            "environments": envs
        }
        with open(self.envs_file, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)

    def add_environment(self, env_name: str) -> bool:
        clean_name = env_name.strip()
        if not clean_name:
            return False
        envs = self.get_environments()
        if clean_name not in envs:
            envs.append(clean_name)
            active = self.get_active_environment()
            data = {"active_env": active, "environments": envs}
            with open(self.envs_file, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
            env_file = os.path.join(self.data_dir, f"{clean_name}.json")
            if not os.path.exists(env_file):
                self._seed_env_file(clean_name, env_file)
            return True
        return False

    def remove_environment(self, env_name: str) -> bool:
        envs = self.get_environments()
        if env_name in envs:
            if len(envs) <= 1:
                return False
            envs.remove(env_name)
            active = self.get_active_environment()
            if active == env_name:
                active = envs[0]
            data = {"active_env": active, "environments": envs}
            with open(self.envs_file, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
            env_file = os.path.join(self.data_dir, f"{env_name}.json")
            if os.path.exists(env_file):
                try:
                    os.remove(env_file)
                except Exception:
                    pass
            return True
        return False

    def get_env_file_path(self, env_name: str) -> str:
        return os.path.join(self.data_dir, f"{env_name}.json")

    def get_environment_data(self, env_name: str) -> Dict[str, Any]:
        path = self.get_env_file_path(env_name)
        if os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                pass
        self._seed_env_file(env_name, path)
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)

    def save_environment_data(self, env_name: str, data: Dict[str, Any]):
        data["last_updated"] = time.time()
        path = self.get_env_file_path(env_name)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)

    def get_variables(self, env_name: str) -> Dict[str, Any]:
        data = self.get_environment_data(env_name)
        return data.get("variables", {})

    def set_variable(self, env_name: str, key: str, value: Any):
        data = self.get_environment_data(env_name)
        if "variables" not in data:
            data["variables"] = {}
        data["variables"][key] = value
        self.save_environment_data(env_name, data)

    def delete_variable(self, env_name: str, key: str) -> bool:
        data = self.get_environment_data(env_name)
        if "variables" in data and key in data["variables"]:
            del data["variables"][key]
            self.save_environment_data(env_name, data)
            return True
        return False

    def get_datasets(self, env_name: str) -> Dict[str, List[Dict[str, Any]]]:
        data = self.get_environment_data(env_name)
        return data.get("datasets", {})

    def save_dataset(self, env_name: str, dataset_name: str, records: List[Dict[str, Any]]):
        data = self.get_environment_data(env_name)
        if "datasets" not in data:
            data["datasets"] = {}
        data["datasets"][dataset_name] = records
        self.save_environment_data(env_name, data)

    def delete_dataset(self, env_name: str, dataset_name: str) -> bool:
        data = self.get_environment_data(env_name)
        if "datasets" in data and dataset_name in data["datasets"]:
            del data["datasets"][dataset_name]
            self.save_environment_data(env_name, data)
            return True
        return False

    def scrape_test_data_from_url(self, target_url: str, browser_channel: str = "msedge") -> Dict[str, Any]:
        result = {
            "url": target_url,
            "title": "",
            "variables": {},
            "datasets": {}
        }
        try:
            with sync_playwright() as p:
                launch_opts = {"headless": True}
                if browser_channel in ("msedge", "chrome"):
                    launch_opts["channel"] = browser_channel
                try:
                    browser = p.chromium.launch(**launch_opts)
                except Exception:
                    browser = p.chromium.launch(headless=True)

                page = browser.new_page(viewport={"width": 1280, "height": 800})
                page.goto(target_url, timeout=20000)
                page.wait_for_load_state("domcontentloaded")
                time.sleep(1)

                result["title"] = page.title()
                result["variables"]["target_url"] = target_url
                result["variables"]["page_title"] = page.title()

                extracted_inputs = page.evaluate("""() => {
                    const inputs = Array.from(document.querySelectorAll('input, select, textarea'));
                    return inputs.map(el => {
                        const name = el.getAttribute('name') || el.id || el.getAttribute('placeholder') || el.getAttribute('data-testid') || '';
                        const type = el.getAttribute('type') || el.tagName.toLowerCase();
                        const val = el.value || '';
                        return { name, type, val };
                    }).filter(i => i.name);
                }""")

                for inp in extracted_inputs:
                    k = inp["name"].replace("-", "_").replace(" ", "_").lower()
                    if k:
                        result["variables"][k] = inp["val"] or f"sample_{k}"

                tables = page.evaluate("""() => {
                    const tableNodes = Array.from(document.querySelectorAll('table'));
                    return tableNodes.map((tbl, tblIdx) => {
                        const headers = Array.from(tbl.querySelectorAll('th')).map(th => th.innerText.trim());
                        const rows = Array.from(tbl.querySelectorAll('tr')).map(tr => {
                            return Array.from(tr.querySelectorAll('td')).map(td => td.innerText.trim());
                        }).filter(r => r.length > 0);
                        return { tblIdx, headers, rows };
                    });
                }""")

                for tbl_info in tables:
                    headers = tbl_info.get("headers") or []
                    rows = tbl_info.get("rows") or []
                    if not headers and rows:
                        headers = [f"col_{i+1}" for i in range(len(rows[0]))]
                    clean_headers = [h.replace(" ", "_").lower() or f"col_{i}" for i, h in enumerate(headers)]
                    dataset_rows = []
                    for row in rows[:30]:
                        row_dict = {}
                        for idx, val in enumerate(row):
                            col_name = clean_headers[idx] if idx < len(clean_headers) else f"col_{idx+1}"
                            row_dict[col_name] = val
                        if row_dict:
                            dataset_rows.append(row_dict)
                    if dataset_rows:
                        t_name = f"table_{tbl_info.get('tblIdx', 1) + 1}"
                        result["datasets"][t_name] = dataset_rows

                list_items = page.evaluate("""() => {
                    const items = Array.from(document.querySelectorAll('.todo-list li, ul.items li, .list-group-item'));
                    return items.map(li => li.innerText.trim()).filter(Boolean);
                }""")
                if list_items:
                    result["datasets"]["scraped_items"] = [{"item_name": item, "status": "scraped"} for item in list_items[:25]]

                browser.close()
        except Exception as e:
            result["error"] = str(e)

        return result
