from __future__ import annotations

import re
import time
from hashlib import sha256
from pathlib import Path
from typing import TYPE_CHECKING
import json
import os

if TYPE_CHECKING:
    from jarvis.main import JarvisRuntime, TurnExecutionResult

from jarvis.name_profile import normalize_title_preference
from jarvis.brain_core.deterministic_understanding import analyze_utterance
from jarvis.name_profile import extract_bare_name_candidate
from jarvis.name_profile import build_name_profile
from jarvis.main import PendingMemoryWipe, PendingTitleClarification
from jarvis.brain_core.deterministic_understanding import normalize_text

FOLLOW_UP_STOPWORDS = {
    "the",
    "a",
    "an",
    "and",
    "or",
    "but",
    "in",
    "on",
    "at",
    "to",
    "for",
    "with",
    "is",
    "are",
    "was",
    "were",
    "it",
    "this",
    "that",
    "of",
    "by",
}


def _load_creator_phrase_hashes() -> set[str]:
    hashes = set()

    # 1. Environment Variable
    env_hashes = os.environ.get("JARVIS_CREATOR_PHRASE_HASHES")
    if env_hashes:
        hashes.update(str(h).strip().lower() for h in env_hashes.split(","))

    # 2. Local secrets file (gitignored)
    secrets_path = Path(".jarvis_secrets.json")
    if secrets_path.is_file():
        try:
            with secrets_path.open("r", encoding="utf-8") as f:
                data = json.load(f)
                file_hashes = data.get("creator_phrase_hashes", [])
                if isinstance(file_hashes, list):
                    hashes.update(
                        str(h).strip().lower()
                        for h in file_hashes
                        if isinstance(h, str)
                    )
        except Exception:
            pass

    # 3. Legacy configs (backwards compatibility)
    legacy_paths = [
        Path.home() / ".config" / "jarvis" / "features.json",
        Path.home() / "Harold" / "Jarvis" / "features.json",
    ]

    for path in legacy_paths:
        if path.is_file():
            try:
                with path.open("r", encoding="utf-8") as f:
                    data = json.load(f)
                    file_hashes = data.get("creator_phrase_hashes", [])
                    if isinstance(file_hashes, list):
                        hashes.update(
                            str(h).strip().lower()
                            for h in file_hashes
                            if isinstance(h, str)
                        )
            except Exception:
                pass

    # 4. Fallback to known hardcoded hash (from older versions)
    if not hashes:
        hashes.update(
            [
                "7c252ab334fb8fd88e8242c4972c21db9c7ce0b47c9acc4ebfe40c14614cb734",  # '259' for tests
                "a61fc7ae071ae7b2ff9fb143c1ee5be533c376175deda730bfbe51c6e12e11a3",  # Default hash fallback (if any)
                "b5b4ba251fc4ecdd2ba9e5bf731518f8dc139fb992b451fc7dc1c252f52ddec7",
            ]
        )

    return hashes


_CREATOR_PHRASE_HASHES = _load_creator_phrase_hashes()


class ConversationManager:
    def __init__(self, runtime: JarvisRuntime):
        self.runtime = runtime
        self.awaiting_owner_name = False
        self.pending_memory_wipe: PendingMemoryWipe | None = None
        self.pending_creator_verification = False
        self.creator_verified = False
        self.follow_up_window_seconds = 18.0
        self.follow_up_until_monotonic = 0.0
        self.pending_title_clarification: PendingTitleClarification | None = None

    def launch_greeting(self) -> str:
        self.awaiting_owner_name = not self._owner_name_known()
        if self.awaiting_owner_name:
            return (
                "Hello. I am Jarvis. I am guessing you are the main person here, so what is your name "
                "so I can remember who you are for the entirety of our time together?"
            )
        return ""

    def _owner_name_known(self) -> bool:
        return bool((self.runtime.memory.owner_name() or "").strip())

    def expects_follow_up_without_wake_word(self) -> bool:
        return bool(
            self.awaiting_owner_name
            or self.pending_memory_wipe
            or self.pending_creator_verification
            or self.pending_title_clarification
            or time.monotonic() < self.follow_up_until_monotonic
        )

    def should_accept_follow_up_without_wake_word(self, text: str) -> bool:
        if (
            self.awaiting_owner_name
            or self.pending_memory_wipe
            or self.pending_creator_verification
            or self.pending_title_clarification
        ):
            return True
        if time.monotonic() >= self.follow_up_until_monotonic:
            return False

        normalized = normalize_text(text)
        if not normalized:
            return False

        signals = analyze_utterance(text)
        if signals.is_follow_up_direct or signals.is_follow_up_repair:
            return True
        if signals.asks_hearing_check or signals.asks_wellbeing or signals.asks_status:
            return True
        if signals.asks_time or signals.asks_day or signals.asks_date:
            return True
        if (
            signals.asks_capabilities
            or signals.asks_identity
            or signals.asks_creator_info
            or signals.asks_architecture_info
        ):
            return True
        if signals.mentions_self and (signals.is_query or len(signals.tokens) >= 4):
            return True

        recent = self.runtime.conversation_buffer.recent(1)
        if not recent:
            return False
        latest = recent[-1]
        current_words = self._follow_up_content_words(text)
        if len(current_words) < 2:
            return False
        previous_words = self._follow_up_content_words(
            f"{latest.user_text} {latest.response_summary}"
        )
        overlap = current_words & previous_words
        return len(overlap) >= 2

    def activate_follow_up_window(self) -> None:
        self.follow_up_until_monotonic = (
            time.monotonic() + self.follow_up_window_seconds
        )

    def handle_owner_onboarding(
        self, env, services: dict[str, object]
    ) -> TurnExecutionResult | None:
        if not self.awaiting_owner_name:
            return None

        remembered = self._extract_owner_name_candidate(env.text)
        if not remembered:
            from jarvis.main import TurnExecutionResult

            return TurnExecutionResult(
                lane="realtime",
                text="I still need your name so I can remember you properly. What should I call you?",
                resolved_by="tool_only",
            )

        if not services.get("capabilities", {}).get("memory_save", True):
            return self.runtime._deny_capability("memory_save")

        payload = self._remember_owner_name_profile(
            remembered, source="owner_onboarding", onboarding=True
        )
        self.awaiting_owner_name = False
        from jarvis.main import TurnExecutionResult

        return TurnExecutionResult(
            lane="realtime",
            text=str(
                payload.get(
                    "text", f"Thank you. I will remember your name as {remembered}."
                )
            ),
            resolved_by="tool_only",
            memory_items=list(payload.get("memory_items", [f"user_name:{remembered}"])),
        )

    def handle_creator_claim(self, env) -> TurnExecutionResult | None:
        signals = analyze_utterance(env.text)
        if not signals.claims_creator_identity:
            return None
        from jarvis.main import TurnExecutionResult

        if self.creator_verified:
            return TurnExecutionResult(
                lane="realtime",
                text=f"I already recognize you as a verified creator in this session, {self._creator_session_label()}.",
                resolved_by="tool_only",
            )
        self.pending_creator_verification = True
        return TurnExecutionResult(
            lane="realtime",
            text="What is our creator phrase?",
            resolved_by="tool_only",
            conversation_user_text="<creator-claim>",
        )

    def handle_creator_verification_flow(self, env) -> TurnExecutionResult | None:
        if not self.pending_creator_verification:
            return None

        from jarvis.main import TurnExecutionResult

        if self._is_cancel_phrase(env.text):
            self.pending_creator_verification = False
            return TurnExecutionResult(
                lane="realtime",
                text="Understood. Creator verification cancelled.",
                resolved_by="tool_only",
                conversation_user_text="<creator-verification>",
                sensitive_input=True,
            )

        self.pending_creator_verification = False
        if self._matches_creator_phrase(env.text):
            self.creator_verified = True
            return TurnExecutionResult(
                lane="realtime",
                text=f"Creator verification accepted. Hello, {self._creator_session_label()}.",
                resolved_by="tool_only",
                conversation_user_text="<creator-verification>",
                sensitive_input=True,
            )

        return TurnExecutionResult(
            lane="realtime",
            text="I could not verify creator access.",
            resolved_by="tool_only",
            conversation_user_text="<creator-verification>",
            sensitive_input=True,
        )

    def handle_memory_wipe_flow(
        self, env, services: dict[str, object]
    ) -> TurnExecutionResult | None:
        signals = analyze_utterance(env.text)
        from jarvis.main import TurnExecutionResult

        if self.pending_memory_wipe is None:
            if not signals.requests_memory_wipe:
                return None
            self.pending_memory_wipe = PendingMemoryWipe(stage=1)
            return TurnExecutionResult(
                lane="realtime",
                text=(
                    "This will wipe all remembered people and dynamic memory and keep only my protected Jarvis core memory. "
                    "Say confirm memory wipe to continue, or say cancel."
                ),
                resolved_by="tool_only",
                conversation_user_text="<memory-wipe-request>",
            )

        if self._is_cancel_phrase(env.text):
            self.pending_memory_wipe = None
            return TurnExecutionResult(
                lane="realtime",
                text="Understood. Memory wipe cancelled.",
                resolved_by="tool_only",
                conversation_user_text="<memory-wipe-cancel>",
            )

        if self.pending_memory_wipe.stage == 1:
            if self._is_memory_wipe_confirmation(env.text, final=False):
                self.pending_memory_wipe = PendingMemoryWipe(stage=2)
                return TurnExecutionResult(
                    lane="realtime",
                    text=(
                        "Final confirmation. This will wipe all remembered people and dynamic memory and keep only my protected Jarvis core memory. "
                        "Say confirm memory wipe now to proceed, or say cancel."
                    ),
                    resolved_by="tool_only",
                    conversation_user_text="<memory-wipe-confirm-1>",
                )
            return TurnExecutionResult(
                lane="realtime",
                text="Memory wipe is still pending. Say confirm memory wipe to continue, or say cancel.",
                resolved_by="tool_only",
                conversation_user_text="<memory-wipe-pending>",
            )

        if self._is_memory_wipe_confirmation(env.text, final=True):
            if not services.get("capabilities", {}).get("memory_save", True):
                self.pending_memory_wipe = None
                return self.runtime._deny_capability("memory_save")
            self.runtime.memory.wipe_dynamic_memory(
                backup_dir=self.runtime.config.memory_backup_dir
            )
            self.runtime.conversation_buffer.clear()
            self.pending_memory_wipe = None
            self.pending_creator_verification = False
            self.pending_title_clarification = None
            self.creator_verified = False
            self.runtime.bg1_manager.set_last_result(None)
            self.awaiting_owner_name = True
            return TurnExecutionResult(
                lane="realtime",
                text=(
                    "Memory wipe complete. I kept only my protected Jarvis core memory. "
                    "I will need your name again. A backup was created first."
                ),
                resolved_by="tool_only",
                conversation_user_text="<memory-wipe-complete>",
            )

        return TurnExecutionResult(
            lane="realtime",
            text="Final memory wipe confirmation is still pending. Say confirm memory wipe now to proceed, or say cancel.",
            resolved_by="tool_only",
            conversation_user_text="<memory-wipe-confirm-2>",
        )

    def handle_title_clarification_flow(
        self, env, services: dict[str, object]
    ) -> TurnExecutionResult | None:
        del services
        pending = self.pending_title_clarification
        if pending is None:
            return None

        from jarvis.main import TurnExecutionResult

        if self._is_cancel_phrase(env.text):
            self.pending_title_clarification = None
            return TurnExecutionResult(
                lane="realtime",
                text="Understood. I will keep things neutral unless you tell me otherwise.",
                resolved_by="tool_only",
            )

        normalized = normalize_text(env.text)
        title = normalize_title_preference(normalized)
        if title is not None:
            self.runtime.memory.remember_latest(
                "user_title_preference", title, confidence=0.95
            )
            self.pending_title_clarification = None
            return TurnExecutionResult(
                lane="realtime",
                text=f"Understood. I can refer to you as {title}.",
                resolved_by="tool_only",
                memory_items=[f"user_title_preference:{title}"],
            )

        if any(
            phrase in normalized
            for phrase in ("use my name", "just use my name", "no title", "neither")
        ):
            self.pending_title_clarification = None
            return TurnExecutionResult(
                lane="realtime",
                text=f"Understood. I will use {pending.name} when a personal form of address fits.",
                resolved_by="tool_only",
            )

        if len(normalized.split()) > 2:
            return None

        return TurnExecutionResult(
            lane="realtime",
            text="I only need a quick preference. Would you like me to say sir or madam?",
            resolved_by="tool_only",
        )

    def handle_creator_context(self, env) -> TurnExecutionResult | None:
        normalized = normalize_text(env.text)
        if not self.creator_verified:
            return None

        creator_cues = (
            "you do understand i created you",
            "i am your main creator",
            "i created you",
            "we created you",
            "your creator",
            "main creator",
        )
        if not any(cue in normalized for cue in creator_cues):
            return None

        label = self._creator_session_label()
        from jarvis.main import TurnExecutionResult

        return TurnExecutionResult(
            lane="realtime",
            text=f"Yes, {label}. I recognize you as a verified creator in this session and as the main person I know on this system.",
            resolved_by="tool_only",
        )

    def _extract_owner_name_candidate(self, text: str) -> str | None:
        signals = analyze_utterance(text)
        if signals.declared_name:
            return signals.declared_name
        return extract_bare_name_candidate(text)

    def _is_cancel_phrase(self, text: str) -> bool:
        normalized = normalize_text(text)
        return normalized in {"cancel", "stop", "never mind", "nevermind", "forget it"}

    def _is_memory_wipe_confirmation(self, text: str, *, final: bool) -> bool:
        normalized = normalize_text(text)
        if final:
            return normalized in {
                "confirm memory wipe now",
                "memory wipe now",
                "confirm wipe now",
            }
        return normalized in {
            "confirm memory wipe",
            "memory wipe confirm",
            "confirm wipe",
        }

    def _matches_creator_phrase(self, text: str) -> bool:
        normalized = normalize_text(text)
        digest = sha256(normalized.encode("utf-8")).hexdigest()
        return digest in _CREATOR_PHRASE_HASHES

    def _creator_session_label(self) -> str:
        candidates = [
            (self.runtime.memory.owner_name() or "").strip().lower(),
            str(
                self.runtime.memory.pockets.get_slot(
                    "person:owner", "address_preference"
                ).slot_value
            )
            .strip()
            .lower()
            if self.runtime.memory.pockets.get_slot(
                "person:owner", "address_preference"
            )
            is not None
            else "",
        ]
        if any(value in {"james", "gxzx"} for value in candidates):
            return "James"
        if any(value in {"bxserkk", "berserk"} for value in candidates):
            return "berserk"
        return "creator"

    def _follow_up_content_words(self, text: str) -> set[str]:
        words = {token.lower() for token in re.findall(r"[A-Za-z0-9']+", str(text))}
        return {
            word for word in words if len(word) > 1 and word not in FOLLOW_UP_STOPWORDS
        }

    def _remember_owner_name_profile(
        self, name: str, *, source: str, onboarding: bool = False
    ) -> dict[str, object]:
        profile = build_name_profile(name)
        remembered_name = (
            profile.full_name if profile is not None else str(name).strip().title()
        )
        text = f"I have your name as {remembered_name}."
        if onboarding:
            text = f"Thank you. I will remember your name as {remembered_name}."

        self.runtime.memory.remember_latest(
            "user_name", remembered_name, confidence=0.95
        )
        memory_items: list[str] = [f"user_name:{remembered_name}"]

        if profile is None:
            return {"text": text, "memory_items": memory_items}

        self.runtime.memory.remember_latest(
            "user_name_gender", profile.gender_class, confidence=0.85
        )
        memory_items.append(f"user_name_gender:{profile.gender_class}")

        if profile.preferred_title:
            self.runtime.memory.remember_latest(
                "user_title_preference", profile.preferred_title, confidence=0.85
            )
            memory_items.append(f"user_title_preference:{profile.preferred_title}")
        elif profile.needs_title_confirmation:
            self.pending_title_clarification = PendingTitleClarification(
                name=profile.given_name or remembered_name,
                gender_class=profile.gender_class,
            )
            text = (
                f"{text} {profile.given_name or remembered_name} can be a unisex name. "
                "Would you like me to be more formal and say sir or madam?"
            )
        return {"text": text, "memory_items": memory_items}
