"""Self-Knowledge Index: Structured runtime self-inspection for Jarvis.

At startup (or from cache), builds a structured self-index of:
- Runtime modules and their roles
- Voice modules (STT, TTS, audio device)
- Routing modules (dispatcher, deterministic understanding)
- BG1 worker modules
- Tool registrations and capabilities
- Addon system
- Memory system
- Config / launcher info

Jarvis answers self-questions from this structured data,
not from vague model memory.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


@dataclass
class ModuleInfo:
    """Information about a Python module in the Jarvis codebase."""

    module_name: str
    file_path: str
    role: str  # runtime, voice, routing, bg1, tool, addon, memory, config, model, world_model, observability
    description: str
    size_bytes: int = 0
    line_count: int = 0
    classes: list[str] = field(default_factory=list)
    functions: list[str] = field(default_factory=list)


@dataclass
class ToolInfo:
    """Information about a registered tool."""

    tool_name: str
    purpose: str
    module_path: str
    lane_policy: str = "either"  # realtime, bg1, either
    latency_class: str = "moderate"
    domain_tags: list[str] = field(default_factory=list)


@dataclass
class CapabilityInfo:
    """Information about a Jarvis capability."""

    capability_name: str
    description: str
    modules: list[str] = field(default_factory=list)
    tools: list[str] = field(default_factory=list)
    voice_friendly_summary: str = ""


@dataclass
class SelfKnowledgeSnapshot:
    """Complete self-knowledge snapshot of the Jarvis runtime."""

    timestamp: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    # Module registry
    runtime_modules: list[ModuleInfo] = field(default_factory=list)
    voice_modules: list[ModuleInfo] = field(default_factory=list)
    routing_modules: list[ModuleInfo] = field(default_factory=list)
    bg1_modules: list[ModuleInfo] = field(default_factory=list)
    tool_modules: list[ModuleInfo] = field(default_factory=list)
    addon_modules: list[ModuleInfo] = field(default_factory=list)
    memory_modules: list[ModuleInfo] = field(default_factory=list)
    config_modules: list[ModuleInfo] = field(default_factory=list)
    model_modules: list[ModuleInfo] = field(default_factory=list)
    world_model_modules: list[ModuleInfo] = field(default_factory=list)
    observability_modules: list[ModuleInfo] = field(default_factory=list)

    # Tool registry
    tools: list[ToolInfo] = field(default_factory=list)

    # Capabilities
    capabilities: list[CapabilityInfo] = field(default_factory=list)

    # Launcher info
    launcher_scripts: list[str] = field(default_factory=list)
    config_locations: list[str] = field(default_factory=list)
    python_version: str = ""
    platform: str = ""

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "timestamp": self.timestamp,
            "runtime_modules": [_module_to_dict(m) for m in self.runtime_modules],
            "voice_modules": [_module_to_dict(m) for m in self.voice_modules],
            "routing_modules": [_module_to_dict(m) for m in self.routing_modules],
            "bg1_modules": [_module_to_dict(m) for m in self.bg1_modules],
            "tool_modules": [_module_to_dict(m) for m in self.tool_modules],
            "addon_modules": [_module_to_dict(m) for m in self.addon_modules],
            "memory_modules": [_module_to_dict(m) for m in self.memory_modules],
            "config_modules": [_module_to_dict(m) for m in self.config_modules],
            "model_modules": [_module_to_dict(m) for m in self.model_modules],
            "world_model_modules": [
                _module_to_dict(m) for m in self.world_model_modules
            ],
            "observability_modules": [
                _module_to_dict(m) for m in self.observability_modules
            ],
            "tools": [
                {
                    "tool_name": t.tool_name,
                    "purpose": t.purpose,
                    "module_path": t.module_path,
                    "lane_policy": t.lane_policy,
                    "latency_class": t.latency_class,
                    "domain_tags": t.domain_tags,
                }
                for t in self.tools
            ],
            "capabilities": [
                {
                    "capability_name": c.capability_name,
                    "description": c.description,
                    "modules": c.modules,
                    "tools": c.tools,
                    "voice_friendly_summary": c.voice_friendly_summary,
                }
                for c in self.capabilities
            ],
            "launcher_scripts": self.launcher_scripts,
            "config_locations": self.config_locations,
            "python_version": self.python_version,
            "platform": self.platform,
        }


def _module_to_dict(m: ModuleInfo) -> dict[str, Any]:
    return {
        "module_name": m.module_name,
        "file_path": m.file_path,
        "role": m.role,
        "description": m.description,
        "size_bytes": m.size_bytes,
        "line_count": m.line_count,
        "classes": m.classes,
        "functions": m.functions,
    }


# ── Module role mappings ───────────────────────────────────────────

_BRAIN_CORE_ROLES: dict[str, tuple[str, str]] = {
    "runtime_v2": (
        "runtime",
        "Phase 2 runtime mixin with turn tracking and evidence packets",
    ),
    "turn_artifact": ("runtime", "Complete structured record of a single turn"),
    "turn_context": ("runtime", "Expanded context packet for routing and follow-ups"),
    "turn_state_machine": ("runtime", "Turn lifecycle state machine"),
    "evidence_packet": ("runtime", "Strict structured facts for LLM compilation"),
    "contracts": ("runtime", "Core data contracts and envelope types"),
    "deterministic_understanding": (
        "routing",
        "Deterministic intent detection from utterance analysis",
    ),
    "prompt_dispatcher": ("routing", "Route selection and task classification"),
    "reference_resolver": ("routing", "Vague reference resolution (it/that/they/why)"),
    "semantic_command_match": ("routing", "Semantic command matching for fuzzy intent"),
    "task_classifier": ("routing", "Task complexity classification for lane selection"),
    "task_router": ("routing", "Task routing to appropriate lane"),
    "intent_handlers": ("routing", "Handler functions for all recognized intents"),
    "response_compiler": ("runtime", "Evidence packet compilation for LLM response"),
    "cllm_renderer": ("runtime", "LLM model interaction for response rendering"),
    "speech_formatter": ("runtime", "Voice-friendly formatting of responses"),
    "bg1_lane": ("bg1", "BG1 background lane management"),
    "bg1_queue": ("bg1", "BG1 task queue with TTL and priority"),
    "bg1_worker": ("bg1", "BG1 background worker execution"),
    "bg1_narrator": ("bg1", "Natural spoken narration for BG1 lifecycle events"),
    "memory_service": ("memory", "SQLite-backed memory with semantic search and decay"),
    "memory_namespaces": (
        "memory",
        "Structured memory namespaces (hot, session, user, task)",
    ),
    "tool_orchestrator": (
        "runtime",
        "Tool execution with capability and confirmation gates",
    ),
    "tool_policy": ("runtime", "Lane-aware tool registry with structured metadata"),
    "debug_trace": ("observability", "Structured JSONL debug trace logging"),
    "ingress_hub": ("runtime", "Raw event ingestion hub"),
    "ingress_normalizer": ("runtime", "Input normalization and profile mapping"),
    "lane_coordinator": ("runtime", "Lane selection coordination"),
    "realtime_lane": ("runtime", "Realtime lane execution"),
    "output_coordinator": ("runtime", "Output delivery coordination"),
    "output_mode": ("runtime", "Output mode selection"),
    "conversation_buffer": ("runtime", "Recent conversation turn buffer"),
    "fallback_policy": ("runtime", "Fallback handling policy"),
    "retry_policy": ("runtime", "Retry decision policy"),
    "guardrails": ("runtime", "Safety guardrails and confirmation gates"),
    "admission_control": ("runtime", "BG1 admission control and rate limiting"),
    "network_guard": ("runtime", "Network access guard"),
    "addon_manager": ("addon", "Addon lifecycle management"),
    "addon_registry": ("addon", "Addon registration and discovery"),
    "addon_audio_pipeline": ("addon", "Addon audio channel pipeline"),
    "addon_channel_state": ("addon", "Addon channel state tracking"),
    "addon_command_registry": ("addon", "Addon command registration"),
    "addon_health": ("addon", "Addon health monitoring"),
    "addon_permissions": ("addon", "Addon permission management"),
    "job_status_service": ("runtime", "Job status tracking service"),
}

_TOOL_ROLES: dict[str, tuple[str, str]] = {
    "time_tool": ("utility", "Local time and UTC time"),
    "datetime_tool": ("utility", "Date/time operations"),
    "calculator": ("utility", "Mathematical expression evaluation"),
    "file_read": ("file", "File reading"),
    "file_write": ("file", "File writing (requires confirmation)"),
    "file_search": ("file", "File search and discovery"),
    "code_runner": ("code", "Python code execution (requires confirmation)"),
    "web_search": ("web", "Web search queries"),
    "web_fetch_http": ("web", "HTTP page fetching"),
    "web_scrape_chromium": ("web", "Chromium-based web scraping"),
    "web_crawl_chromium": ("web", "Multi-page Chromium crawling"),
    "web_extract_main_text": ("web", "Main text extraction from HTML"),
    "web_fetch_extract": ("web", "Fetch and extract web page content"),
    "web_structured_extract": ("web", "Structured data extraction from pages"),
    "web_paginate": ("web", "Web page pagination handling"),
    "url_normalize": ("web", "URL normalization utilities"),
    "screen_capture": ("vision", "Screen capture and screenshot"),
    "ocr_read": ("vision", "OCR text extraction from images"),
    "vision_lite": ("vision", "Lightweight vision analysis"),
    "active_window_info": ("system", "Active window information"),
    "app_ops": ("system", "Application launch and focus operations"),
    "memory_tool": ("memory", "Memory inspection and management"),
    "job_status_tool": ("system", "Job status querying tool"),
    "download_file": ("file", "File download from URL"),
    "document_parse": ("file", "Document parsing"),
    "research_brief": ("research", "Research brief generation"),
    "artifact_store": ("file", "Artifact storage management"),
    "addon_control": ("addon", "Addon control commands"),
    "route_control": ("system", "Route control commands"),
    "template_response": ("utility", "Template response generation"),
    "source_cite_builder": ("utility", "Source citation building"),
    "captcha_detect": ("web", "CAPTCHA detection"),
    "robots_rate_limit_guard": ("web", "Robots.txt and rate limit guard"),
    "network_guard": ("system", "Network access guard"),
    "specialist_code": ("code", "Code specialist tool bridge"),
    "specialist_vision": ("vision", "Vision specialist tool bridge"),
}

_VOICE_ROLES: dict[str, tuple[str, str]] = {
    "runtime": ("voice", "Voice runtime loop (STT + TTS integration)"),
    "stt": ("voice", "Speech-to-text engine"),
    "tts": ("voice", "Text-to-speech engine"),
    "tts_state": ("voice", "TTS state machine with watchdog and fallback"),
    "audio_device": ("voice", "Audio device management"),
    "diagnostics": ("voice", "Voice system diagnostics"),
}


# ── Capability definitions ─────────────────────────────────────────

_CAPABILITIES: list[dict[str, Any]] = [
    {
        "name": "time_and_date",
        "description": "Tell the current time, day, and date",
        "modules": ["tools.time_tool", "tools.datetime_tool"],
        "tools": ["local_now", "utc_now_iso"],
        "voice_summary": "I can tell you the current time, day, and date.",
    },
    {
        "name": "web_research",
        "description": "Search the web, fetch pages, and extract information",
        "modules": [
            "tools.web_search",
            "tools.web_fetch_http",
            "tools.web_scrape_chromium",
        ],
        "tools": ["web_search", "web_fetch", "web_scrape"],
        "voice_summary": "I can search the web, check websites, and extract information from pages.",
    },
    {
        "name": "code_analysis",
        "description": "Inspect, audit, and work with code and repositories",
        "modules": ["specialists.specialist_code", "tools.code_runner"],
        "tools": ["code_runner", "specialist_code"],
        "voice_summary": "I can inspect code, audit repositories, and run Python code.",
    },
    {
        "name": "vision",
        "description": "Screen capture, OCR, and visual analysis",
        "modules": ["tools.screen_capture", "tools.ocr_read", "tools.vision_lite"],
        "tools": ["screen_capture", "ocr_read", "vision_lite"],
        "voice_summary": "I can capture your screen, read text from images, and analyze visual content.",
    },
    {
        "name": "file_operations",
        "description": "Read, write, search, and manage files",
        "modules": ["tools.file_read", "tools.file_write", "tools.file_search"],
        "tools": ["file_read", "file_write", "file_search"],
        "voice_summary": "I can read, write, and search files on the system.",
    },
    {
        "name": "memory",
        "description": "Remember and recall facts, preferences, and past findings",
        "modules": ["brain_core.memory_service", "brain_core.memory_namespaces"],
        "tools": ["memory_tool"],
        "voice_summary": "I can remember things you tell me and recall them later.",
    },
    {
        "name": "calculations",
        "description": "Evaluate mathematical expressions",
        "modules": ["tools.calculator"],
        "tools": ["calculator"],
        "voice_summary": "I can do calculations and evaluate mathematical expressions.",
    },
    {
        "name": "application_control",
        "description": "Launch and focus applications",
        "modules": ["tools.app_ops"],
        "tools": ["app_launch", "app_focus"],
        "voice_summary": "I can open and switch between applications on your system.",
    },
    {
        "name": "background_tasks",
        "description": "Long-running research, code, and analysis tasks",
        "modules": ["brain_core.bg1_queue", "brain_core.bg1_worker"],
        "tools": [],
        "voice_summary": "I can handle long-running research and analysis tasks in the background.",
    },
]


class SelfKnowledgeIndex:
    """Builds and serves structured self-knowledge about the Jarvis runtime.

    On build, scans the codebase to create a structured index of:
    - All modules and their roles
    - All tools and their capabilities
    - All capabilities and their summaries
    - Launcher and config information

    Answers self-questions from structured data, not model memory.
    """

    def __init__(self, jarvis_package_dir: str | None = None) -> None:
        self._jarvis_dir = jarvis_package_dir or str(
            Path(__file__).resolve().parent.parent
        )
        self._snapshot: SelfKnowledgeSnapshot | None = None

    def build(self) -> SelfKnowledgeSnapshot:
        """Build or rebuild the self-knowledge index."""
        snapshot = SelfKnowledgeSnapshot(
            python_version=sys.version.split()[0],
            platform=sys.platform,
        )

        jarvis_dir = Path(self._jarvis_dir)

        # Scan brain_core modules
        brain_core_dir = jarvis_dir / "brain_core"
        if brain_core_dir.is_dir():
            for py_file in sorted(brain_core_dir.glob("*.py")):
                if py_file.name.startswith("_"):
                    continue
                module_name = py_file.stem
                role_info = _BRAIN_CORE_ROLES.get(
                    module_name, ("runtime", f"Brain core module: {module_name}")
                )
                info = self._scan_module(py_file, role_info[0], role_info[1])
                self._categorize_module(snapshot, info)

        # Scan tool modules
        tools_dir = jarvis_dir / "tools"
        if tools_dir.is_dir():
            for py_file in sorted(tools_dir.glob("*.py")):
                if py_file.name.startswith("_"):
                    continue
                module_name = py_file.stem
                role_info = _TOOL_ROLES.get(
                    module_name, ("utility", f"Tool module: {module_name}")
                )
                info = self._scan_module(py_file, "tool", role_info[1])
                info.role = "tool"
                snapshot.tool_modules.append(info)

        # Scan voice modules
        voice_dir = jarvis_dir / "voice"
        if voice_dir.is_dir():
            for py_file in sorted(voice_dir.glob("*.py")):
                if py_file.name.startswith("_"):
                    continue
                module_name = py_file.stem
                role_info = _VOICE_ROLES.get(
                    module_name, ("voice", f"Voice module: {module_name}")
                )
                info = self._scan_module(py_file, "voice", role_info[1])
                snapshot.voice_modules.append(info)

        # Scan model modules
        models_dir = jarvis_dir / "models"
        if models_dir.is_dir():
            for py_file in sorted(models_dir.glob("*.py")):
                if py_file.name.startswith("_"):
                    continue
                info = self._scan_module(
                    py_file, "model", f"Model module: {py_file.stem}"
                )
                snapshot.model_modules.append(info)

        # Scan world_model modules
        wm_dir = jarvis_dir / "world_model"
        if wm_dir.is_dir():
            for py_file in sorted(wm_dir.glob("*.py")):
                if py_file.name.startswith("_"):
                    continue
                info = self._scan_module(
                    py_file, "world_model", f"World model: {py_file.stem}"
                )
                snapshot.world_model_modules.append(info)

        # Scan observability modules
        obs_dir = jarvis_dir / "observability"
        if obs_dir.is_dir():
            for py_file in sorted(obs_dir.glob("*.py")):
                if py_file.name.startswith("_"):
                    continue
                info = self._scan_module(
                    py_file, "observability", f"Observability: {py_file.stem}"
                )
                snapshot.observability_modules.append(info)

        # Build tool info from role mappings
        for tool_name, (domain, desc) in _TOOL_ROLES.items():
            snapshot.tools.append(
                ToolInfo(
                    tool_name=tool_name,
                    purpose=desc,
                    module_path=f"jarvis.tools.{tool_name}",
                    domain_tags=[domain],
                )
            )

        # Build capabilities
        for cap_def in _CAPABILITIES:
            snapshot.capabilities.append(
                CapabilityInfo(
                    capability_name=cap_def["name"],
                    description=cap_def["description"],
                    modules=cap_def["modules"],
                    tools=cap_def["tools"],
                    voice_friendly_summary=cap_def["voice_summary"],
                )
            )

        # Launcher scripts
        root = jarvis_dir.parent
        for script_name in (
            "launch_jarvis.bat",
            "start_jarvis.bat",
            "run_voice.py",
            "run_chat.py",
        ):
            script = root / script_name
            if script.exists():
                snapshot.launcher_scripts.append(str(script))

        # Config locations
        config_file = jarvis_dir / "config.py"
        if config_file.exists():
            snapshot.config_locations.append(str(config_file))
        env_example = root / ".env.example"
        if env_example.exists():
            snapshot.config_locations.append(str(env_example))

        self._snapshot = snapshot
        return snapshot

    def get_snapshot(self) -> SelfKnowledgeSnapshot:
        """Get current snapshot, building if needed."""
        if self._snapshot is None:
            self.build()
        return self._snapshot  # type: ignore

    # ── Query methods ────────────────────────────────────────────────

    def answer_tools_question(self) -> str:
        """Answer 'what tools do you have?' from structured data."""
        snapshot = self.get_snapshot()
        tool_lines = []
        for tool in snapshot.tools:
            tool_lines.append(f"- {tool.tool_name}: {tool.purpose}")
        return "Here are my available tools:\n" + "\n".join(tool_lines)

    def answer_capabilities_question(self) -> str:
        """Answer 'what can you do?' from structured data."""
        snapshot = self.get_snapshot()
        lines = []
        for cap in snapshot.capabilities:
            lines.append(f"- {cap.voice_friendly_summary}")
        return "Here's what I can do:\n" + "\n".join(lines)

    def answer_codebase_question(self, query: str | None = None) -> str:
        """Answer 'how are you built?' from structured data."""
        snapshot = self.get_snapshot()
        all_modules = (
            snapshot.runtime_modules
            + snapshot.voice_modules
            + snapshot.routing_modules
            + snapshot.bg1_modules
            + snapshot.tool_modules
            + snapshot.addon_modules
            + snapshot.memory_modules
            + snapshot.model_modules
            + snapshot.world_model_modules
            + snapshot.observability_modules
        )
        total_loc = sum(m.line_count for m in all_modules)
        counts = {
            "runtime": len(snapshot.runtime_modules),
            "voice": len(snapshot.voice_modules),
            "routing": len(snapshot.routing_modules),
            "bg1": len(snapshot.bg1_modules),
            "tool": len(snapshot.tool_modules),
            "addon": len(snapshot.addon_modules),
            "memory": len(snapshot.memory_modules),
            "model": len(snapshot.model_modules),
            "world_model": len(snapshot.world_model_modules),
            "observability": len(snapshot.observability_modules),
        }
        total = sum(counts.values())
        return (
            f"I'm built from {total} Python modules across {len(counts)} subsystems "
            f"with {total_loc:,} total lines of code. "
            f"My core runtime has {counts['runtime']} modules, "
            f"routing has {counts['routing']}, "
            f"I have {counts['tool']} tool modules, "
            f"{counts['voice']} voice modules, "
            f"and {counts['memory']} memory modules. "
            f"I'm running on Python {snapshot.python_version} on {snapshot.platform}."
        )

    def answer_architecture_question(self, query: str | None = None) -> str:
        """Answer 'what is your architecture?' from structured data."""
        snapshot = self.get_snapshot()
        return (
            "My architecture has a unified pipeline: "
            "ingress and normalization, reference resolution, "
            "memory retrieval, deterministic and contextual routing, "
            "tool execution in realtime or background lanes, "
            "evidence packet compilation, LLM response rendering, "
            "and voice delivery with TTS. "
            f"I have {len(snapshot.tools)} tools, "
            f"{len(snapshot.capabilities)} capability areas, "
            "and a world model with belief state tracking and fact anchoring."
        )

    def answer_module_location(self, module_keyword: str) -> str:
        """Answer 'where is [module]?' from structured data."""
        snapshot = self.get_snapshot()
        keyword = module_keyword.lower()
        matches = []

        all_modules = (
            snapshot.runtime_modules
            + snapshot.voice_modules
            + snapshot.routing_modules
            + snapshot.bg1_modules
            + snapshot.tool_modules
            + snapshot.addon_modules
            + snapshot.memory_modules
            + snapshot.model_modules
            + snapshot.world_model_modules
            + snapshot.observability_modules
        )

        for mod in all_modules:
            if keyword in mod.module_name.lower() or keyword in mod.description.lower():
                matches.append(mod)

        if not matches:
            return f"I couldn't find a module matching '{module_keyword}'."

        lines = []
        for m in matches[:5]:
            lines.append(f"- {m.module_name} ({m.role}): {m.file_path}")
            if m.description:
                lines.append(f"  {m.description}")

        return (
            f"Found {len(matches)} module(s) matching '{module_keyword}':\n"
            + "\n".join(lines)
        )

    # ── Internal ─────────────────────────────────────────────────────

    def _scan_module(self, path: Path, role: str, description: str) -> ModuleInfo:
        """Scan a Python file for classes and functions."""
        classes: list[str] = []
        functions: list[str] = []
        line_count = 0
        size_bytes = 0

        try:
            size_bytes = path.stat().st_size
            content = path.read_text(encoding="utf-8", errors="replace")
            lines = content.splitlines()
            line_count = len(lines)

            for line in lines:
                stripped = line.strip()
                if stripped.startswith("class ") and "(" in stripped:
                    class_name = stripped.split("(")[0].replace("class ", "").strip()
                    if class_name and not class_name.startswith("_"):
                        classes.append(class_name)
                elif stripped.startswith("def ") and "(" in stripped:
                    func_name = stripped.split("(")[0].replace("def ", "").strip()
                    if func_name and not func_name.startswith("_"):
                        functions.append(func_name)
        except (OSError, UnicodeDecodeError):
            pass

        return ModuleInfo(
            module_name=path.stem,
            file_path=str(path),
            role=role,
            description=description,
            size_bytes=size_bytes,
            line_count=line_count,
            classes=classes,
            functions=functions,
        )

    def _categorize_module(
        self, snapshot: SelfKnowledgeSnapshot, info: ModuleInfo
    ) -> None:
        """Categorize a module into the appropriate snapshot list."""
        role = info.role
        if role == "runtime":
            snapshot.runtime_modules.append(info)
        elif role == "voice":
            snapshot.voice_modules.append(info)
        elif role == "routing":
            snapshot.routing_modules.append(info)
        elif role == "bg1":
            snapshot.bg1_modules.append(info)
        elif role == "tool":
            snapshot.tool_modules.append(info)
        elif role == "addon":
            snapshot.addon_modules.append(info)
        elif role == "memory":
            snapshot.memory_modules.append(info)
        elif role == "config":
            snapshot.config_modules.append(info)
        elif role == "model":
            snapshot.model_modules.append(info)
        elif role == "world_model":
            snapshot.world_model_modules.append(info)
        elif role == "observability":
            snapshot.observability_modules.append(info)
        else:
            snapshot.runtime_modules.append(info)
