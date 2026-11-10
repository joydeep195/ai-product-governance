#!/usr/bin/env python3
"""Deterministic AI inventory scan for the ai-product-governance skill.

Lists evidence of AI in a product or repository, so the governance gates work on the AI
that actually exists and a product with no AI gets a clean result:

  * known AI SDKs and ML frameworks declared in dependency manifests;
  * imports of those SDKs in Python and JavaScript/TypeScript source;
  * model API endpoints and OpenAI-compatible API paths in source and config files;
  * names of AI API-key environment variables (never their values);
  * model weight files and prompt files;
  * AI developer tooling (coding-assistant configuration), listed separately because it
    shapes how the product is built, not what the product does.

It is a starting point, not proof. It says what it does not cover, and the agent completes
the inventory with its own file and search tools and by asking the user. The scan is
read-only, makes no network calls and follows no symbolic links. It prints file paths, line
numbers and matched names, never the content of a line, so secrets cannot leak into its
output. The same files always produce the same result.

Standard library only; runs on Python 3.9+.

Usage:
  python ai_inventory.py [PATH ...] [--format json|md] [--max-files N]

PATH defaults to the current directory. Exit codes: 0 the scan completed, whether or not it
found AI; 2 a path does not exist or an argument is invalid.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional, Sequence, Tuple

MAX_FILE_BYTES = 1_000_000
DEFAULT_MAX_FILES = 50_000
MAX_LISTED = 200
SELF = Path(__file__).resolve()

# Directories that hold installed dependencies, build output or caches, not the product's own code.
SKIP_DIRS = {
    ".git", ".hg", ".svn", "node_modules", ".venv", "venv", "__pycache__", ".tox", ".nox", ".mypy_cache",
    ".pytest_cache", ".ruff_cache", "dist", "build", "target", "vendor", ".next", ".nuxt", "bower_components",
    ".gradle", ".idea", ".terraform", "site-packages", "coverage", ".cache",
}  # fmt: skip
TEXT_SUFFIXES = {
    ".py", ".ipynb", ".js", ".mjs", ".cjs", ".ts", ".mts", ".cts", ".tsx", ".jsx", ".go", ".rs", ".rb", ".php",
    ".java", ".kt", ".kts", ".scala", ".cs", ".swift", ".dart", ".ex", ".exs", ".r", ".jl", ".lua", ".sh", ".ps1",
    ".tf", ".yaml", ".yml", ".json", ".toml", ".ini", ".cfg", ".conf", ".properties", ".xml", ".env", ".example",
    ".sample", ".template", ".vue", ".svelte", ".sql",
}  # fmt: skip
PYTHON_SUFFIXES = {".py", ".ipynb"}
JS_SUFFIXES = {".js", ".mjs", ".cjs", ".ts", ".mts", ".cts", ".tsx", ".jsx", ".vue", ".svelte"}
MODEL_SUFFIXES = {".onnx", ".safetensors", ".gguf", ".ggml", ".pt", ".pth", ".tflite", ".mlmodel", ".keras", ".joblib"}
PROMPT_FILE = re.compile(r"(\.prompty?|\.prompt\.(md|txt|ya?ml|json))$", re.IGNORECASE)
PROMPT_DIRS = {"prompts", "prompt_templates", "prompt-templates"}
PROMPT_DIR_SUFFIXES = {".md", ".txt", ".yaml", ".yml", ".json", ".j2", ".jinja", ".hbs", ".mustache"}

# AI coding-assistant configuration: how the product is built, not what it does.
DEV_TOOL_FILES = {
    "CLAUDE.md": "Claude Code instructions",
    "AGENTS.md": "AGENTS.md instructions for coding agents",
    "GEMINI.md": "Gemini CLI instructions",
    ".cursorrules": "Cursor rules",
    ".windsurfrules": "Windsurf rules",
    "copilot-instructions.md": "GitHub Copilot instructions",
}
DEV_TOOL_DIRS = {
    ".claude": "Claude Code configuration",
    ".cursor": "Cursor configuration",
    ".codex": "Codex configuration",
    ".windsurf": "Windsurf configuration",
}

# Known AI packages per ecosystem: name -> what it is. A trailing "*" matches a prefix.
PYPI = {
    "openai": "OpenAI SDK", "anthropic": "Anthropic SDK", "google-generativeai": "Google Gemini SDK (legacy)",
    "google-genai": "Google Gen AI SDK", "google-cloud-aiplatform": "Google Vertex AI SDK",
    "vertexai": "Google Vertex AI SDK", "cohere": "Cohere SDK", "mistralai": "Mistral SDK", "groq": "Groq SDK",
    "together": "Together AI SDK", "replicate": "Replicate SDK", "huggingface-hub": "Hugging Face Hub",
    "transformers": "Hugging Face Transformers", "sentence-transformers": "Sentence Transformers",
    "langchain": "LangChain", "langchain-*": "LangChain integration", "langgraph": "LangGraph",
    "llama-index": "LlamaIndex", "llama-index-*": "LlamaIndex integration", "litellm": "LiteLLM",
    "ollama": "Ollama client", "azure-ai-inference": "Azure AI Inference SDK",
    "azure-ai-ml": "Azure Machine Learning SDK", "semantic-kernel": "Semantic Kernel", "dspy": "DSPy",
    "dspy-ai": "DSPy", "instructor": "Instructor", "haystack-ai": "Haystack", "crewai": "CrewAI",
    "pyautogen": "AutoGen", "autogen-agentchat": "AutoGen", "ag2": "AG2", "pydantic-ai": "Pydantic AI",
    "smolagents": "smolagents", "openai-agents": "OpenAI Agents SDK", "claude-agent-sdk": "Claude Agent SDK",
    "mcp": "MCP SDK (tools for AI agents)", "llama-cpp-python": "llama.cpp bindings", "vllm": "vLLM",
    "torch": "PyTorch (ML framework)", "tensorflow": "TensorFlow (ML framework)", "keras": "Keras (ML framework)",
    "jax": "JAX (ML framework)", "scikit-learn": "scikit-learn (ML framework)", "xgboost": "XGBoost (ML framework)",
    "lightgbm": "LightGBM (ML framework)", "catboost": "CatBoost (ML framework)", "onnxruntime": "ONNX Runtime",
    "spacy": "spaCy (NLP)", "mlflow": "MLflow (model lifecycle)",
}  # fmt: skip
PY_MODULES = {
    "openai": "OpenAI SDK", "anthropic": "Anthropic SDK", "google.generativeai": "Google Gemini SDK (legacy)",
    "google.genai": "Google Gen AI SDK", "google.cloud.aiplatform": "Google Vertex AI SDK",
    "vertexai": "Google Vertex AI SDK", "cohere": "Cohere SDK", "mistralai": "Mistral SDK", "groq": "Groq SDK",
    "together": "Together AI SDK", "replicate": "Replicate SDK", "huggingface_hub": "Hugging Face Hub",
    "transformers": "Hugging Face Transformers", "sentence_transformers": "Sentence Transformers",
    "langchain": "LangChain", "langchain_*": "LangChain integration", "langgraph": "LangGraph",
    "llama_index": "LlamaIndex", "litellm": "LiteLLM", "ollama": "Ollama client",
    "azure.ai.inference": "Azure AI Inference SDK", "semantic_kernel": "Semantic Kernel", "dspy": "DSPy",
    "instructor": "Instructor", "haystack": "Haystack", "crewai": "CrewAI", "autogen": "AutoGen",
    "autogen_agentchat": "AutoGen", "pydantic_ai": "Pydantic AI", "smolagents": "smolagents",
    "claude_agent_sdk": "Claude Agent SDK", "llama_cpp": "llama.cpp bindings", "vllm": "vLLM",
    "torch": "PyTorch (ML framework)", "tensorflow": "TensorFlow (ML framework)", "keras": "Keras (ML framework)",
    "jax": "JAX (ML framework)", "sklearn": "scikit-learn (ML framework)", "xgboost": "XGBoost (ML framework)",
    "lightgbm": "LightGBM (ML framework)", "catboost": "CatBoost (ML framework)", "onnxruntime": "ONNX Runtime",
    "spacy": "spaCy (NLP)", "mlflow": "MLflow (model lifecycle)",
}  # fmt: skip
NPM = {
    "openai": "OpenAI SDK", "@anthropic-ai/sdk": "Anthropic SDK", "@anthropic-ai/*": "Anthropic SDK",
    "@google/generative-ai": "Google Gemini SDK (legacy)", "@google/genai": "Google Gen AI SDK",
    "@google-cloud/vertexai": "Google Vertex AI SDK", "cohere-ai": "Cohere SDK", "@mistralai/mistralai": "Mistral SDK",
    "groq-sdk": "Groq SDK", "together-ai": "Together AI SDK", "replicate": "Replicate SDK",
    "@huggingface/inference": "Hugging Face Inference", "@huggingface/transformers": "Transformers.js",
    "@xenova/transformers": "Transformers.js", "langchain": "LangChain", "@langchain/*": "LangChain integration",
    "llamaindex": "LlamaIndex", "ai": "Vercel AI SDK", "@ai-sdk/*": "Vercel AI SDK provider", "ollama": "Ollama client",
    "@azure/openai": "Azure OpenAI SDK", "@azure-rest/ai-inference": "Azure AI Inference SDK",
    "@aws-sdk/client-bedrock-runtime": "Amazon Bedrock SDK",
    "@aws-sdk/client-bedrock-agent-runtime": "Amazon Bedrock SDK",
    "@tensorflow/tfjs": "TensorFlow.js (ML framework)", "@tensorflow/tfjs-node": "TensorFlow.js (ML framework)",
    "onnxruntime-node": "ONNX Runtime", "onnxruntime-web": "ONNX Runtime",
    "@modelcontextprotocol/sdk": "MCP SDK (tools for AI agents)", "@openai/agents": "OpenAI Agents SDK",
    "@mastra/core": "Mastra",
}  # fmt: skip
GO = {
    "github.com/sashabaranov/go-openai": "OpenAI client", "github.com/openai/openai-go*": "OpenAI SDK",
    "github.com/anthropics/anthropic-sdk-go*": "Anthropic SDK", "github.com/google/generative-ai-go": "Google Gemini SDK",
    "google.golang.org/genai": "Google Gen AI SDK", "github.com/tmc/langchaingo": "LangChainGo",
    "github.com/ollama/ollama": "Ollama", "github.com/aws/aws-sdk-go-v2/service/bedrockruntime": "Amazon Bedrock SDK",
    "github.com/cohere-ai/cohere-go*": "Cohere SDK", "github.com/mark3labs/mcp-go": "MCP SDK (tools for AI agents)",
}  # fmt: skip
CARGO = {
    "async-openai": "OpenAI client", "openai-api-rs": "OpenAI client", "ollama-rs": "Ollama client",
    "candle-core": "Candle (ML framework)", "tch": "PyTorch bindings (ML framework)", "ort": "ONNX Runtime",
    "rig-core": "Rig (LLM framework)", "rmcp": "MCP SDK (tools for AI agents)",
}  # fmt: skip
GEMS = {
    "ruby-openai": "OpenAI client",
    "openai": "OpenAI client",
    "anthropic": "Anthropic SDK",
    "langchainrb": "LangChain.rb",
}
COMPOSER = {
    "openai-php/client": "OpenAI client",
    "openai-php/laravel": "OpenAI client",
    "theodo-group/llphant": "LLPhant",
}
MAVEN = {
    "com.openai:openai-java*": "OpenAI SDK", "com.anthropic:anthropic-java*": "Anthropic SDK",
    "dev.langchain4j:*": "LangChain4j", "org.springframework.ai:*": "Spring AI",
    "com.google.cloud:google-cloud-aiplatform": "Google Vertex AI SDK", "com.google.genai:google-genai": "Google Gen AI SDK",
    "software.amazon.awssdk:bedrockruntime": "Amazon Bedrock SDK", "com.azure:azure-ai-openai": "Azure OpenAI SDK",
    "com.azure:azure-ai-inference": "Azure AI Inference SDK", "ai.djl:*": "Deep Java Library (ML framework)",
}  # fmt: skip
NUGET = {
    "openai": "OpenAI SDK", "anthropic": "Anthropic SDK", "anthropic.sdk": "Anthropic client",
    "azure.ai.openai": "Azure OpenAI SDK", "azure.ai.inference": "Azure AI Inference SDK",
    "microsoft.semantickernel*": "Semantic Kernel", "microsoft.extensions.ai*": "Microsoft.Extensions.AI",
    "llamasharp*": "LLamaSharp", "microsoft.ml*": "ML.NET (ML framework)",
    "google.cloud.aiplatform.v1": "Google Vertex AI SDK", "awssdk.bedrockruntime": "Amazon Bedrock SDK",
    "ollamasharp": "Ollama client", "modelcontextprotocol*": "MCP SDK (tools for AI agents)",
}  # fmt: skip

ENDPOINTS: List[Tuple["re.Pattern[str]", str]] = [
    (re.compile(r"api\.openai\.com"), "OpenAI API"),
    (re.compile(r"api\.anthropic\.com"), "Anthropic API"),
    (re.compile(r"generativelanguage\.googleapis\.com"), "Google Gemini API"),
    (re.compile(r"aiplatform\.googleapis\.com"), "Google Vertex AI"),
    (re.compile(r"[a-z0-9-]+\.openai\.azure\.com"), "Azure OpenAI"),
    (re.compile(r"[a-z0-9-]+\.services\.ai\.azure\.com"), "Azure AI Foundry"),
    (re.compile(r"bedrock-runtime"), "Amazon Bedrock"),
    (re.compile(r"api\.mistral\.ai"), "Mistral API"),
    (re.compile(r"api\.cohere\.(?:ai|com)"), "Cohere API"),
    (re.compile(r"api\.groq\.com"), "Groq API"),
    (re.compile(r"api\.together\.(?:xyz|ai)"), "Together AI API"),
    (re.compile(r"openrouter\.ai/api"), "OpenRouter"),
    (re.compile(r"api\.deepseek\.com"), "DeepSeek API"),
    (re.compile(r"api\.x\.ai"), "xAI API"),
    (re.compile(r"api\.perplexity\.ai"), "Perplexity API"),
    (re.compile(r"api-inference\.huggingface\.co|router\.huggingface\.co"), "Hugging Face Inference"),
    (re.compile(r"api\.replicate\.com"), "Replicate API"),
    (re.compile(r"(?:localhost|127\.0\.0\.1):11434"), "Ollama (local model server)"),
    (re.compile(r"/v1/chat/completions|/v1/embeddings"), "OpenAI-compatible API path (gateway or self-hosted model)"),
    (re.compile(r":(?:stream)?[gG]enerateContent"), "Gemini API method"),
]
KEY_VARIABLES = re.compile(
    r"\b(OPENAI_API_KEY|OPENAI_ORG(?:ANIZATION)?_ID|AZURE_OPENAI_(?:API_KEY|ENDPOINT|DEPLOYMENT\w*)|ANTHROPIC_API_KEY|"
    r"CLAUDE_API_KEY|GEMINI_API_KEY|GOOGLE_GENAI_USE_VERTEXAI|MISTRAL_API_KEY|COHERE_API_KEY|CO_API_KEY|"
    r"GROQ_API_KEY|TOGETHER_API_KEY|OPENROUTER_API_KEY|DEEPSEEK_API_KEY|XAI_API_KEY|PERPLEXITY_API_KEY|HF_TOKEN|"
    r"HUGGINGFACEHUB_API_TOKEN|HUGGING_FACE_HUB_TOKEN|REPLICATE_API_TOKEN|LANGCHAIN_API_KEY|LANGSMITH_API_KEY|"
    r"OLLAMA_HOST|LITELLM_MASTER_KEY)\b"
)
PY_IMPORT = re.compile(
    r"^\s*(?:from\s+([A-Za-z_][\w.]*)\s+import\b|import\s+([A-Za-z_][\w.]*(?:\s*,\s*[A-Za-z_][\w.]*)*))"
)
JS_IMPORT = re.compile(
    r"""(?:\bfrom\s*|\bimport\s*\(?\s*|\brequire\s*\(\s*)["']((?:@[\w.-]+/)?[\w.-]+)(?:/[^"']*)?["']"""
)

NOT_COVERED = [
    "Imports in languages other than Python and JavaScript/TypeScript that no manifest declares, and transitive "
    "dependencies that only lockfiles list: search the source for them",
    "AI behind internal gateways or proxies with their own hostnames and paths, and SDKs this scan does not know",
    "AI features inside third-party SaaS the product relies on (support desk, CRM, analytics, office suites): "
    "ask the user",
    "Runtime configuration, secrets and infrastructure outside the scanned paths, and other repositories",
    "Rules-based or statistical models built without a known ML library, for example scoring formulas in SQL "
    "or spreadsheets",
    "Files larger than 1 MB, binary files other than model weights, Markdown and other documentation, and "
    "directories of installed dependencies, build output and caches (see skipped_directories)",
]


def _match(name: str, catalogue: Dict[str, str]) -> Optional[str]:
    for known, label in catalogue.items():
        if known.endswith("*"):
            if name.startswith(known[:-1]):
                return label
        elif name == known:
            return label
    return None


def _line_of(text: str, offset: int) -> int:
    return text.count("\n", 0, offset) + 1


# --------------------------------------------------------------------------- manifests

MANIFEST_NAMES = {
    "pyproject.toml": "pypi", "Pipfile": "pypi", "setup.py": "pypi", "setup.cfg": "pypi",
    "environment.yml": "pypi", "environment.yaml": "pypi", "package.json": "npm", "go.mod": "go",
    "Cargo.toml": "cargo", "Gemfile": "gems", "composer.json": "composer", "pom.xml": "maven",
    "build.gradle": "maven", "build.gradle.kts": "maven", "packages.config": "nuget",
    "Directory.Packages.props": "nuget",
}  # fmt: skip
_REQ_LINE = re.compile(r"^\s*([A-Za-z0-9][A-Za-z0-9._-]*)")
_QUOTED_REQ = re.compile(r"""["']([A-Za-z0-9][A-Za-z0-9._-]*)\s*(?:\[[^\]]*\])?\s*(?=[<>=!~;@,\s"'])""")
_TOML_KEY = re.compile(r"^\s*([A-Za-z0-9][A-Za-z0-9._-]*)\s*=", re.MULTILINE)
_YAML_ITEM = re.compile(r"^\s*-\s*([A-Za-z0-9][A-Za-z0-9._-]*)", re.MULTILINE)
_GO_MODULE = re.compile(r"((?:github\.com|google\.golang\.org|golang\.org|gopkg\.in)/[^\s\"]+)")
_GEM = re.compile(r"""^\s*gem\s+["']([^"']+)["']""", re.MULTILINE)
_MAVEN = re.compile(r"<groupId>\s*([^<\s]+)\s*</groupId>\s*<artifactId>\s*([^<\s]+)\s*</artifactId>")
_GRADLE = re.compile(r"""["']([A-Za-z0-9_.\-]+):([A-Za-z0-9_.\-]+)(?::[^"']*)?["']""")
_NUGET = re.compile(r"""(?:Include|Update|id)\s*=\s*["']([A-Za-z0-9_.\-]+)["']""")


def manifest_ecosystem(name: str) -> Optional[str]:
    """Return the package ecosystem of a dependency manifest, or None if the file is not one."""
    if name in MANIFEST_NAMES:
        return MANIFEST_NAMES[name]
    if re.match(r"^(requirements|constraints)[\w.-]*\.(txt|in)$", name, re.IGNORECASE):
        return "pypi"
    if name.endswith((".csproj", ".fsproj", ".vbproj")):
        return "nuget"
    return None


def _regex_names(text: str, pattern: "re.Pattern[str]") -> Iterator[Tuple[str, int]]:
    for match in pattern.finditer(text):
        yield match.group(1), _line_of(text, match.start(1))


def _python_names(name: str, text: str) -> Iterator[Tuple[str, int]]:
    if name.lower().endswith((".txt", ".in")):
        for number, line in enumerate(text.splitlines(), 1):
            match = _REQ_LINE.match(line)
            if match and not line.lstrip().startswith(("#", "-")):
                yield match.group(1), number
        return
    for pattern in (_QUOTED_REQ, _TOML_KEY, _YAML_ITEM):
        yield from _regex_names(text, pattern)


def _json_dependency_names(text: str, sections: Sequence[str]) -> Iterator[Tuple[str, int]]:
    try:
        data = json.loads(text)
    except ValueError:
        return
    if not isinstance(data, dict):
        return
    for section in sections:
        block = data.get(section)
        if isinstance(block, dict):
            for dependency in block:
                found = re.search('"' + re.escape(dependency) + r'"\s*:', text)
                yield dependency, _line_of(text, found.start()) if found else 1


def scan_manifest(name: str, ecosystem: str, text: str) -> List[Tuple[str, str, int]]:
    """Return (package, what it is, line) for each known AI package a manifest declares."""
    candidates: List[Tuple[str, int]]
    catalogue: Dict[str, str]
    if ecosystem == "pypi":
        candidates = [(re.sub(r"[-_.]+", "-", n).lower(), line) for n, line in _python_names(name, text)]
        catalogue = PYPI
    elif ecosystem == "npm":
        sections = ("dependencies", "devDependencies", "peerDependencies", "optionalDependencies")
        candidates, catalogue = list(_json_dependency_names(text, sections)), NPM
    elif ecosystem == "composer":
        candidates = [(n.lower(), line) for n, line in _json_dependency_names(text, ("require", "require-dev"))]
        catalogue = COMPOSER
    elif ecosystem == "go":
        candidates, catalogue = list(_regex_names(text, _GO_MODULE)), GO
    elif ecosystem == "cargo":
        candidates, catalogue = list(_regex_names(text, _TOML_KEY)), CARGO
    elif ecosystem == "gems":
        candidates, catalogue = list(_regex_names(text, _GEM)), GEMS
    elif ecosystem == "maven":
        matches = [*_MAVEN.finditer(text), *_GRADLE.finditer(text)]
        candidates = [(f"{m.group(1)}:{m.group(2)}", _line_of(text, m.start())) for m in matches]
        catalogue = MAVEN
    elif ecosystem == "nuget":
        candidates = [(n.lower(), line) for n, line in _regex_names(text, _NUGET)]
        catalogue = NUGET
    else:
        return []
    found: Dict[str, Tuple[str, str, int]] = {}
    for package, line in candidates:
        label = _match(package, catalogue)
        if label and package not in found:
            found[package] = (package, label, line)
    return list(found.values())


# --------------------------------------------------------------------------- source files


def _python_imports(line: str) -> List[str]:
    match = PY_IMPORT.match(line)
    if not match:
        return []
    if match.group(1):
        return [match.group(1)]
    return [part.strip() for part in match.group(2).split(",")]


def _module_label(module: str) -> Optional[Tuple[str, str]]:
    parts = module.split(".")
    for size in range(len(parts), 0, -1):
        candidate = ".".join(parts[:size])
        label = _match(candidate, PY_MODULES)
        if label:
            return candidate, label
    return None


def scan_source_line(line: str, suffix: str) -> List[Tuple[str, str]]:
    """Return (package or module, what it is) for each known AI SDK a source line imports."""
    found: List[Tuple[str, str]] = []
    if suffix in PYTHON_SUFFIXES:
        # A notebook stores each source line as a JSON string: "import openai\n",
        text = line.strip().lstrip('"').replace("\\n", "") if suffix == ".ipynb" else line
        for module in _python_imports(text):
            hit = _module_label(module)
            if hit:
                found.append(hit)
    elif suffix in JS_SUFFIXES:
        for match in JS_IMPORT.finditer(line):
            label = _match(match.group(1), NPM)
            if label:
                found.append((match.group(1), label))
    return found


# --------------------------------------------------------------------------- walking


def _read_text(path: Path) -> Optional[str]:
    try:
        if path.stat().st_size > MAX_FILE_BYTES:
            return None
        data = path.read_bytes()
    except OSError:
        return None
    if b"\0" in data[:8192]:
        return None
    return data.decode("utf-8", errors="replace")


def _is_text(path: Path) -> bool:
    name = path.name.lower()
    return path.suffix.lower() in TEXT_SUFFIXES or name.startswith(".env") or name in {"dockerfile", "makefile"}


def _walk(root: Path, dev_dirs: List[Path]) -> Iterator[Tuple[Path, List[str]]]:
    """Yield (directory, sorted file names), pruning dependency, build, cache and tool directories."""
    if root.is_file():
        yield root.parent, [root.name]
        return
    for current, dirs, names in os.walk(root):
        directory = Path(current)
        dev_dirs.extend(directory / d for d in sorted(dirs) if d in DEV_TOOL_DIRS)
        dirs[:] = sorted(
            d
            for d in dirs
            if d not in SKIP_DIRS
            and d not in DEV_TOOL_DIRS
            and not d.endswith(".egg-info")
            and not (directory / d).is_symlink()
            and not (directory / d / "pyvenv.cfg").exists()
        )
        yield directory, sorted(names)


class _Findings:
    """One entry per (kind, name, file): the first line it appears on, plus an occurrence count where kept."""

    def __init__(self) -> None:
        self._items: Dict[str, Dict[Tuple[str, ...], Dict[str, Any]]] = {}

    def add(self, kind: str, key: Tuple[str, ...], entry: Dict[str, Any]) -> None:
        bucket = self._items.setdefault(kind, {})
        if key not in bucket:
            bucket[key] = entry
        elif "occurrences" in bucket[key]:
            bucket[key]["occurrences"] += 1

    def get(self, kind: str) -> List[Dict[str, Any]]:
        return list(self._items.get(kind, {}).values())


def _scan_file(path: Path, shown: str, findings: _Findings) -> bool:
    """Record the evidence in one file. Returns True if the file is a dependency manifest."""
    name, suffix = path.name, path.suffix.lower()
    ecosystem = manifest_ecosystem(name)
    if ecosystem is None and not _is_text(path):
        return False
    text = _read_text(path)
    if text is None:
        return False
    if ecosystem is not None:
        for package, what, line in scan_manifest(name, ecosystem, text):
            entry = {"package": package, "what": what, "found_in": "manifest", "file": shown, "line": line}
            findings.add("sdks", (package, shown), entry)
    for number, line_text in enumerate(text.splitlines(), 1):
        for module, what in scan_source_line(line_text, suffix):
            entry = {"package": module, "what": what, "found_in": "import", "file": shown, "line": number}
            findings.add("sdks", (module, shown), entry)
        for pattern, what in ENDPOINTS:
            if pattern.search(line_text):
                entry = {"what": what, "file": shown, "line": number, "occurrences": 1}
                findings.add("endpoints", (what, shown), entry)
        for match in KEY_VARIABLES.finditer(line_text):
            variable = match.group(1)
            entry = {"name": variable, "file": shown, "line": number, "occurrences": 1}
            findings.add("key_variables", (variable, shown), entry)
    return ecosystem is not None


def scan(roots: Sequence[Path], max_files: int = DEFAULT_MAX_FILES) -> Dict[str, Any]:
    """Scan files and directories and return a JSON-serialisable AI inventory."""
    findings = _Findings()
    files = manifests = 0
    truncated = False
    for root in roots:
        base = root if root.is_dir() else root.parent
        dev_dirs: List[Path] = []
        for directory, names in _walk(root, dev_dirs):
            in_prompt_dir = directory.name.lower() in PROMPT_DIRS
            copilot_prompts = directory.name == "prompts" and directory.parent.name == ".github"
            for name in names:
                path = directory / name
                if path.is_symlink() or path.resolve() == SELF:
                    continue
                if files >= max_files:
                    truncated = True
                    break
                files += 1
                shown = path.relative_to(base).as_posix()
                suffix = path.suffix.lower()
                if name in DEV_TOOL_FILES or (copilot_prompts and name.endswith(".prompt.md")):
                    what = DEV_TOOL_FILES.get(name, "GitHub Copilot prompt file")
                    findings.add("dev_tools", (shown,), {"what": what, "path": shown})
                elif suffix in MODEL_SUFFIXES:
                    findings.add("model_files", (shown,), {"path": shown, "format": suffix.lstrip(".")})
                else:
                    if PROMPT_FILE.search(name) or (in_prompt_dir and suffix in PROMPT_DIR_SUFFIXES):
                        findings.add("prompt_files", (shown,), {"path": shown})
                    manifests += _scan_file(path, shown, findings)
            if truncated:
                break
        for path in dev_dirs:
            shown = path.relative_to(base).as_posix() + "/"
            findings.add("dev_tools", (shown,), {"what": DEV_TOOL_DIRS[path.name], "path": shown})
        if truncated:
            break

    kinds = ("sdks", "endpoints", "key_variables", "model_files", "prompt_files")
    counts = {kind: len(findings.get(kind)) for kind in kinds}
    ai_found = any(counts.values())
    if ai_found:
        headline = "AI found: " + ", ".join(f"{n} {k.replace('_', ' ')}" for k, n in counts.items() if n)
    else:
        headline = (
            f"No AI found in {files} files scanned. This is not yet proof that the product has no AI: "
            "check everything in not_covered."
        )
    notes = [
        "This scan is a starting point. Complete the inventory with your own file and search tools, ask the user "
        "about everything in not_covered, and record the result in the AI inventory template.",
        "Each entry is one file: it gives the first line where the evidence appears.",
    ]
    if findings.get("dev_tools"):
        notes.append(
            "dev_tools lists AI coding-assistant configuration. It shows how the product is built, not AI in the "
            "product: record it separately, and treat it as a product AI use only if the product ships it to users."
        )
    if truncated:
        notes.append(f"Stopped after {max_files} files: pass --max-files or scan narrower paths.")
    result: Dict[str, Any] = {
        "tool": "ai_inventory",
        "headline": headline,
        "ai_found": ai_found,
        "scanned": {
            "roots": [root.as_posix() for root in roots],
            "files": files,
            "manifests": manifests,
            "truncated": truncated,
            "skipped_directories": sorted(SKIP_DIRS | {"*.egg-info", "virtual environments (pyvenv.cfg)"}),
        },
        "counts": counts,
    }
    for kind in (*kinds, "dev_tools"):
        items = findings.get(kind)
        result[kind] = items[:MAX_LISTED]
        if len(items) > MAX_LISTED:
            notes.append(f"{kind}: listing the first {MAX_LISTED} of {len(items)}.")
    result["not_covered"] = list(NOT_COVERED)
    result["notes"] = notes
    return result


# --------------------------------------------------------------------------- output


def _cell(value: Any) -> str:
    return str(value).replace("|", "\\|")


def render_markdown(result: Dict[str, Any]) -> str:
    scanned = result["scanned"]
    roots = ", ".join(f"`{root}`" for root in scanned["roots"])
    stopped = "; stopped early" if scanned["truncated"] else ""
    out = [
        f"**AI inventory: {result['headline']}**",
        "",
        f"Scanned {scanned['files']} files ({scanned['manifests']} dependency manifests) under {roots}{stopped}.",
        "",
    ]
    tables = [
        ("AI SDKs and ML frameworks", "sdks", ["package", "what", "found_in", "file", "line"]),
        ("Model API endpoints", "endpoints", ["what", "file", "line", "occurrences"]),
        (
            "AI API-key variable names (values are never read out)",
            "key_variables",
            ["name", "file", "line", "occurrences"],
        ),
        ("Model files", "model_files", ["path", "format"]),
        ("Prompt files", "prompt_files", ["path"]),
        ("AI developer tooling (how the product is built, not AI in the product)", "dev_tools", ["what", "path"]),
    ]
    for title, kind, columns in tables:
        items = result[kind]
        if not items:
            continue
        out += [f"**{title}:**", "", "| " + " | ".join(c.replace("_", " ").capitalize() for c in columns) + " |"]
        out.append("|" + "---|" * len(columns))
        out += ["| " + " | ".join(_cell(item.get(c, "")) for c in columns) + " |" for item in items]
        out.append("")
    out += ["**Not covered by this scan** (check these with your own tools or ask the user):", ""]
    out += [f"- {item}" for item in result["not_covered"]]
    out += ["", "**Notes:**", ""] + [f"- {note}" for note in result["notes"]]
    return "\n".join(out) + "\n"


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="List evidence of AI in a product or repository (read-only, no network, no secret values).",
    )
    parser.add_argument("paths", nargs="*", default=["."], help="files or directories to scan (default: .)")
    parser.add_argument("--format", choices=("json", "md"), default="json")
    parser.add_argument("--max-files", type=int, default=DEFAULT_MAX_FILES, help="stop after this many files")
    args = parser.parse_args(argv)
    roots = [Path(p) for p in args.paths]
    missing = [str(p) for p in roots if not p.exists()]
    if missing:
        print("error: no such file or directory: " + ", ".join(missing), file=sys.stderr)
        return 2
    if args.max_files < 1:
        print("error: --max-files must be at least 1", file=sys.stderr)
        return 2
    result = scan(roots, max_files=args.max_files)
    if args.format == "md":
        sys.stdout.write(render_markdown(result))
    else:
        sys.stdout.write(json.dumps(result, indent=2, ensure_ascii=False) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
