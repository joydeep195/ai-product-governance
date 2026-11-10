from __future__ import annotations

import ast
import json
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

from ai_product_governance import engines


@pytest.fixture(scope="module")
def inventory() -> ModuleType:
    return engines.load_engine("ai_inventory")


def write(root: Path, files: dict[str, str]) -> Path:
    for name, text in files.items():
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    return root


def packages(result: dict[str, Any], found_in: str | None = None) -> set[str]:
    return {item["package"] for item in result["sdks"] if found_in is None or item["found_in"] == found_in}


def test_a_product_without_ai_gets_a_clean_result_that_says_what_it_did_not_cover(
    inventory: ModuleType, tmp_path: Path
) -> None:
    write(
        tmp_path,
        {
            "requirements.txt": "flask==3.0.0\nrequests>=2\n",
            "app.py": "import flask\nfrom requests import get\n",
            "package.json": json.dumps({"dependencies": {"react": "^19.0.0"}}),
            "README.md": "We might call api.openai.com one day.\n",
        },
    )
    result = inventory.scan([tmp_path])
    assert result["ai_found"] is False
    assert result["headline"].startswith("No AI found in 4 files scanned")
    assert "not yet proof" in result["headline"]
    assert result["scanned"]["manifests"] == 2
    assert all(result[kind] == [] for kind in ("sdks", "endpoints", "key_variables", "model_files", "prompt_files"))
    assert any("third-party SaaS" in item for item in result["not_covered"])


def test_finds_ai_packages_declared_in_manifests(inventory: ModuleType, tmp_path: Path) -> None:
    write(
        tmp_path,
        {
            "requirements.txt": "openai>=1.40\nLangChain_OpenAI==0.2\n# anthropic is commented out\nnumpy\n",
            "pyproject.toml": '[project]\ndependencies = [\n  "anthropic[vertex]>=0.40",\n  "httpx",\n]\n',
            "web/package.json": json.dumps(
                {"dependencies": {"@anthropic-ai/sdk": "^0.30", "react": "^19"}, "devDependencies": {"ai": "^4"}},
                indent=2,
            ),
            "svc/go.mod": "module x\n\nrequire (\n\tgithub.com/sashabaranov/go-openai v1.36.0\n)\n",
            "app/App.csproj": '<Project><ItemGroup><PackageReference Include="Azure.AI.OpenAI" /></ItemGroup></Project>',
            "api/pom.xml": "<dependency><groupId>dev.langchain4j</groupId><artifactId>langchain4j</artifactId></dependency>",
        },
    )
    result = inventory.scan([tmp_path])
    assert result["ai_found"] is True
    assert packages(result, "manifest") == {
        "openai",
        "langchain-openai",
        "anthropic",
        "@anthropic-ai/sdk",
        "ai",
        "github.com/sashabaranov/go-openai",
        "azure.ai.openai",
        "dev.langchain4j:langchain4j",
    }
    first = next(item for item in result["sdks"] if item["package"] == "anthropic")
    assert (first["file"], first["line"], first["what"]) == ("pyproject.toml", 3, "Anthropic SDK")


def test_finds_sdk_imports_that_no_manifest_declares(inventory: ModuleType, tmp_path: Path) -> None:
    notebook = {"cells": [{"cell_type": "code", "source": ["import pandas as pd\n", "import openai\n"]}]}
    write(
        tmp_path,
        {
            "jobs/score.py": "import os, torch\nfrom google.genai import types\nfrom langchain_community import x\n",
            "web/chat.ts": 'import OpenAI from "openai";\nconst lc = require(\'@langchain/openai\');\nimport "./local";\n',
            "analysis.ipynb": json.dumps(notebook, indent=1),
        },
    )
    result = inventory.scan([tmp_path])
    assert packages(result, "import") == {"torch", "google.genai", "langchain_community", "openai", "@langchain/openai"}
    notebook_hit = next(item for item in result["sdks"] if item["file"] == "analysis.ipynb")
    assert notebook_hit["package"] == "openai"


def test_reports_endpoints_and_key_names_but_never_secret_values(inventory: ModuleType, tmp_path: Path) -> None:
    secret = "sk-proj-DO-NOT-PRINT-1234567890"  # noqa: S105 - a fake value the scan must never print
    write(
        tmp_path,
        {
            ".env.example": f"OPENAI_API_KEY={secret}\nDATABASE_URL=postgres://x\n",
            "config/settings.yaml": "llm:\n  base_url: https://contoso.openai.azure.com/\n",
            "client.py": 'URL = "https://api.anthropic.com/v1/messages"\nURL2 = "https://api.anthropic.com/v1/x"\n',
        },
    )
    result = inventory.scan([tmp_path])
    assert {(v["name"], v["file"]) for v in result["key_variables"]} == {("OPENAI_API_KEY", ".env.example")}
    assert {(e["what"], e["file"]) for e in result["endpoints"]} == {
        ("Azure OpenAI", "config/settings.yaml"),
        ("Anthropic API", "client.py"),
    }
    anthropic = next(e for e in result["endpoints"] if e["what"] == "Anthropic API")
    assert (anthropic["line"], anthropic["occurrences"]) == (1, 2)
    assert secret not in json.dumps(result)
    assert secret not in inventory.render_markdown(result)


def test_model_and_prompt_files_count_as_ai(inventory: ModuleType, tmp_path: Path) -> None:
    (tmp_path / "models").mkdir()
    (tmp_path / "models" / "ranker.onnx").write_bytes(b"\x08\x00binary")
    write(tmp_path, {"prompts/system.md": "You are...", "flows/triage.prompty": "---\n", "docs/guide.md": "Hi"})
    result = inventory.scan([tmp_path])
    assert result["model_files"] == [{"path": "models/ranker.onnx", "format": "onnx"}]
    assert {p["path"] for p in result["prompt_files"]} == {"prompts/system.md", "flows/triage.prompty"}
    assert result["ai_found"] is True


def test_coding_assistant_config_is_listed_apart_and_is_not_product_ai(inventory: ModuleType, tmp_path: Path) -> None:
    write(
        tmp_path,
        {
            "CLAUDE.md": "Use pnpm.",
            ".claude/settings.json": json.dumps({"env": {"ANTHROPIC_API_KEY": "x"}}),
            ".github/copilot-instructions.md": "Be terse.",
            ".github/prompts/review.prompt.md": "Review this.",
            "src/main.py": "print('hello')\n",
        },
    )
    result = inventory.scan([tmp_path])
    assert result["ai_found"] is False
    assert {tool["path"] for tool in result["dev_tools"]} == {
        "CLAUDE.md",
        ".claude/",
        ".github/copilot-instructions.md",
        ".github/prompts/review.prompt.md",
    }
    assert result["key_variables"] == []
    assert any("not AI in the product" in note for note in result["notes"])


def test_skips_dependency_build_and_virtualenv_directories(inventory: ModuleType, tmp_path: Path) -> None:
    write(
        tmp_path,
        {
            "node_modules/openai/package.json": json.dumps({"dependencies": {"openai": "1"}}),
            ".venv/lib/x.py": "import openai\n",
            "env/pyvenv.cfg": "home = /usr\n",
            "env/lib/y.py": "import anthropic\n",
            "dist/bundle.js": 'require("openai")\n',
            "pkg.egg-info/requires.txt": "openai\n",
            "app.py": "x = 1\n",
        },
    )
    result = inventory.scan([tmp_path])
    assert result["ai_found"] is False
    assert result["scanned"]["files"] == 1


def test_scanning_a_single_file_and_several_roots(inventory: ModuleType, tmp_path: Path) -> None:
    write(tmp_path, {"a/requirements.txt": "openai\n", "b/app.js": 'import x from "ollama"\n'})
    one = inventory.scan([tmp_path / "a" / "requirements.txt"])
    assert [(s["package"], s["file"]) for s in one["sdks"]] == [("openai", "requirements.txt")]
    both = inventory.scan([tmp_path / "a", tmp_path / "b"])
    assert packages(both) == {"openai", "ollama"}


def test_results_are_deterministic_and_stop_at_max_files(inventory: ModuleType, tmp_path: Path) -> None:
    write(tmp_path, {f"m{i}/requirements.txt": "openai\n" for i in range(5)})
    assert inventory.scan([tmp_path]) == inventory.scan([tmp_path])
    capped = inventory.scan([tmp_path], max_files=2)
    assert capped["scanned"] == {**capped["scanned"], "files": 2, "truncated": True}
    assert [s["file"] for s in capped["sdks"]] == ["m0/requirements.txt", "m1/requirements.txt"]
    assert any("Stopped after 2 files" in note for note in capped["notes"])


def test_cli_formats_and_exit_codes(inventory: ModuleType, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    write(tmp_path, {"requirements.txt": "anthropic\n"})
    assert inventory.main([str(tmp_path)]) == 0
    assert json.loads(capsys.readouterr().out)["counts"]["sdks"] == 1
    assert inventory.main([str(tmp_path), "--format", "md"]) == 0
    md = capsys.readouterr().out
    assert md.startswith("**AI inventory: AI found: 1 sdks**")
    assert "| anthropic | Anthropic SDK | manifest | requirements.txt | 1 |" in md
    assert "**Not covered by this scan**" in md
    assert inventory.main([str(tmp_path / "missing")]) == 2
    assert "no such file or directory" in capsys.readouterr().err
    assert inventory.main([str(tmp_path), "--max-files", "0"]) == 2


def test_the_scan_skips_its_own_source(inventory: ModuleType, skill: Any) -> None:
    result = inventory.scan([skill.scripts_dir])
    assert all(item["file"] != "ai_inventory.py" for kind in ("endpoints", "key_variables") for item in result[kind])


def test_script_uses_only_the_standard_library(skill: Any) -> None:
    tree = ast.parse((skill.scripts_dir / "ai_inventory.py").read_text(encoding="utf-8"))
    imported = {
        alias.name.split(".")[0] for node in ast.walk(tree) if isinstance(node, ast.Import) for alias in node.names
    }
    imported |= {
        node.module.split(".")[0] for node in ast.walk(tree) if isinstance(node, ast.ImportFrom) and node.module
    }
    assert imported <= set(sys.stdlib_module_names) | {"__future__"}
