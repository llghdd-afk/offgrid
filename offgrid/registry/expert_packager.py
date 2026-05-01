"""
Expert .kwx packager: import/export expert packages.
.kwx format is a zip containing expert.yaml and optional test_cases/, README.md, CHANGELOG.md.
"""

import logging
import os
import shutil
import tempfile
import zipfile
from pathlib import Path

import yaml

from offgrid.registry.expert_loader import ExpertLoader

logger = logging.getLogger(__name__)

USER_EXPERTS_DIR = os.path.join(Path.home(), ".offgrid", "experts")


class ExpertPackager:
    """Import/export expert packages (.kwx format = zip)."""

    @staticmethod
    def export(registry, expert_name: str, output_dir: str = ".") -> str:
        """Export an expert as .kwx package. Returns path to created file."""
        expert = registry.get(expert_name)
        if not expert:
            raise ValueError(f"Expert not found: {expert_name}")

        version = expert.get("version", "0.0.0")
        safe_name = expert_name.replace(" ", "_")
        kwx_name = f"{safe_name}-{version}.kwx"
        kwx_path = os.path.join(os.path.abspath(output_dir), kwx_name)

        # Strip internal fields
        data = {k: v for k, v in expert.items() if not k.startswith("_")}

        os.makedirs(output_dir, exist_ok=True)
        with zipfile.ZipFile(kwx_path, "w", zipfile.ZIP_DEFLATED) as zf:
            yaml_content = yaml.dump(data, allow_unicode=True, default_flow_style=False, sort_keys=False)
            zf.writestr("expert.yaml", yaml_content)

        logger.info("Exported %s to %s", expert_name, kwx_path)
        return kwx_path

    @staticmethod
    def install(kwx_path: str, registry) -> str:
        """
        Install expert from .kwx file or URL.
        Returns expert name.
        """
        if kwx_path.startswith(("http://", "https://")):
            return ExpertPackager.install_from_url(kwx_path, registry)

        kwx_path = os.path.abspath(kwx_path)
        if not os.path.isfile(kwx_path):
            raise FileNotFoundError(f"File not found: {kwx_path}")
        if not zipfile.is_zipfile(kwx_path):
            raise ValueError(f"Not a valid .kwx (zip) file: {kwx_path}")

        with zipfile.ZipFile(kwx_path, "r") as zf:
            names = zf.namelist()
            if "expert.yaml" not in names:
                raise ValueError("Invalid .kwx package: missing expert.yaml")

            try:
                yaml_content = zf.read("expert.yaml").decode("utf-8")
            except UnicodeDecodeError as e:
                raise ValueError(f"Invalid .kwx package: expert.yaml is not valid UTF-8: {e}")
            expert_def = yaml.safe_load(yaml_content)

            valid, err = ExpertLoader.validate(expert_def)
            if not valid:
                raise ValueError(f"Invalid expert definition: {err}")

            # Copy expert.yaml to user experts dir
            os.makedirs(USER_EXPERTS_DIR, exist_ok=True)
            safe_name = expert_def["name"].lower().replace(" ", "_")
            dest = os.path.join(USER_EXPERTS_DIR, f"{safe_name}.yaml")
            with open(dest, "w", encoding="utf-8") as f:
                f.write(yaml_content)

            # Extract optional test_cases/
            for name in names:
                if name.startswith("test_cases/") and not name.endswith("/"):
                    target = os.path.join(USER_EXPERTS_DIR, safe_name + "_tests", os.path.basename(name))
                    os.makedirs(os.path.dirname(target), exist_ok=True)
                    with open(target, "wb") as f:
                        f.write(zf.read(name))

        # Ensure defaults and register
        expert_def.setdefault("lifecycle", "new")
        expert_def.setdefault("performance", {"success_rate": 0.0, "avg_latency_s": 0, "task_count": 0})
        expert_def["_source"] = dest
        registry.register(expert_def)

        logger.info("Installed expert %s from %s", expert_def["name"], kwx_path)
        return expert_def["name"]

    @staticmethod
    def install_from_url(url: str, registry) -> str:
        """Download .kwx from URL and install."""
        import httpx

        with tempfile.TemporaryDirectory() as tmpdir:
            fname = url.rsplit("/", 1)[-1] or "expert.kwx"
            if not fname.endswith(".kwx"):
                fname += ".kwx"
            tmp_path = os.path.join(tmpdir, fname)

            resp = httpx.get(url, follow_redirects=True, timeout=60)
            resp.raise_for_status()
            with open(tmp_path, "wb") as f:
                f.write(resp.content)

            return ExpertPackager.install(tmp_path, registry)

    @staticmethod
    def remove(expert_name: str, registry) -> bool:
        """Remove an installed expert. Returns True if removed."""
        expert = registry.get(expert_name)
        if not expert:
            raise ValueError(f"Expert not found: {expert_name}")

        # Delete YAML file if it's in user dir
        source = expert.get("_source", "")
        if source and os.path.isfile(source) and USER_EXPERTS_DIR in source:
            os.remove(source)
            logger.info("Deleted %s", source)

        # Remove test dir if exists
        safe_name = expert_name.lower().replace(" ", "_")
        test_dir = os.path.join(USER_EXPERTS_DIR, safe_name + "_tests")
        if os.path.isdir(test_dir):
            shutil.rmtree(test_dir)

        # Unregister
        registry.experts.pop(expert_name, None)
        return True

    @staticmethod
    def create_template(name: str) -> str:
        """Create a new expert template YAML in ~/.offgrid/experts/. Returns path."""
        safe_name = name.lower().replace(" ", "_")
        os.makedirs(USER_EXPERTS_DIR, exist_ok=True)
        dest = os.path.join(USER_EXPERTS_DIR, f"{safe_name}.yaml")

        if os.path.exists(dest):
            raise FileExistsError(f"Expert file already exists: {dest}")

        template = {
            "name": name,
            "version": "1.0.0",
            "type": "custom",
            "author": "",
            "created_at": "",
            "trigger_keywords": ["keyword1", "keyword2"],
            "trigger_min_confidence": 0.75,
            "system_prompt": "你是一个专家。请描述你的专长和工作方式。\n",
            "tool_whitelist": ["read_file", "write_file", "run_bash"],
            "pipeline": ["locator", "generator", "verifier"],
            "tested_models": [],
            "performance": {"success_rate": 0.0, "avg_latency_s": 0, "task_count": 0},
            "lifecycle": "new",
        }

        with open(dest, "w", encoding="utf-8") as f:
            yaml.dump(template, f, allow_unicode=True, default_flow_style=False, sort_keys=False)

        logger.info("Created expert template: %s", dest)
        return dest
