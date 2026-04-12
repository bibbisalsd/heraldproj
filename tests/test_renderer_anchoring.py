"""NH-CRSIS Task G: Fact Anchoring in Renderer tests."""
from __future__ import annotations

import pytest
from jarvis.brain_core.cllm_renderer import CLLMRenderer, HEDGE_MARKERS, ESCAPE_MARKERS
from jarvis.brain_core.response_compiler import ResponsePacket, TaggedResponsePacket


class TestFactExtraction:
    """Test _extract_facts method."""

    def test_fact_extraction_from_tool_summaries(self):
        """Verify flat list produced from tool summaries."""
        renderer = CLLMRenderer()
        packet = TaggedResponsePacket(
            user_text="What's the status?",
            facts=["brain:test"],
            constraints=[],
            tone="helpful",
            length_hint="short",
            tool_summaries=["File saved successfully", "Build completed in 2.3s"],
            memory_items=[],
            job_snapshot=None,
        )
        facts = renderer._extract_facts(packet)
        assert "File saved successfully" in facts
        assert "Build completed in 2.3s" in facts

    def test_fact_extraction_includes_job_snapshot(self):
        """Job status string included when present."""
        renderer = CLLMRenderer()
        packet = TaggedResponsePacket(
            user_text="What's the job status?",
            facts=[],
            constraints=[],
            tone="helpful",
            length_hint="short",
            tool_summaries=[],
            memory_items=[],
            job_snapshot={"status": "running", "progress": "45%"},
        )
        facts = renderer._extract_facts(packet)
        assert "Background job status: running" in facts
        assert "Job progress: 45%" in facts

    def test_fact_extraction_from_packet_facts(self):
        """Facts from packet.facts are cleaned and included."""
        renderer = CLLMRenderer()
        packet = TaggedResponsePacket(
            user_text="Test",
            facts=["tool:cleaned fact", "memory:another fact"],
            constraints=[],
            tone="helpful",
            length_hint="short",
            tool_summaries=[],
            memory_items=[],
            job_snapshot=None,
        )
        facts = renderer._extract_facts(packet)
        assert "cleaned fact" in facts
        assert "another fact" in facts

    def test_fact_extraction_empty_packet(self):
        """Empty packet returns empty list."""
        renderer = CLLMRenderer()
        packet = TaggedResponsePacket(
            user_text="Test",
            facts=[],
            constraints=[],
            tone="helpful",
            length_hint="short",
            tool_summaries=[],
            memory_items=[],
            job_snapshot=None,
        )
        facts = renderer._extract_facts(packet)
        assert facts == []


class TestAnchoredPrompt:
    """Test _build_anchored_prompt method."""

    def test_anchored_prompt_contains_enumerated_facts(self):
        """Verify [1], [2] labels present in prompt."""
        renderer = CLLMRenderer()
        facts = ["Fact one", "Fact two", "Fact three"]
        packet = TaggedResponsePacket(
            user_text="Test question",
            facts=[],
            constraints=[],
            tone="helpful",
            length_hint="short",
            tool_summaries=[],
            memory_items=[],
            job_snapshot=None,
        )
        prompt = renderer._build_anchored_prompt(facts, packet)
        assert "[1] Fact one" in prompt
        assert "[2] Fact two" in prompt
        assert "[3] Fact three" in prompt
        assert "PERMITTED FACTS" in prompt

    def test_anchored_prompt_empty_facts(self):
        """No-facts branch produces safe fallback text."""
        renderer = CLLMRenderer()
        facts = []
        packet = TaggedResponsePacket(
            user_text="Test",
            facts=[],
            constraints=[],
            tone="helpful",
            length_hint="short",
            tool_summaries=[],
            memory_items=[],
            job_snapshot=None,
        )
        prompt = renderer._build_anchored_prompt(facts, packet)
        assert "(no facts available)" in prompt
        assert "Do not add facts, estimates, or context from your training data" in prompt

    def test_anchored_prompt_contains_rules(self):
        """Hard scope rules are included in prompt."""
        renderer = CLLMRenderer()
        packet = TaggedResponsePacket(
            user_text="Test",
            facts=[],
            constraints=[],
            tone="helpful",
            length_hint="short",
            tool_summaries=[],
            memory_items=[],
            job_snapshot=None,
        )
        prompt = renderer._build_anchored_prompt(["fact"], packet)
        assert "Do not speculate" in prompt
        assert "Do not hedge" in prompt
        assert "I don't have that information right now" in prompt


class TestOutputGate:
    """Test _gate_output method."""

    def test_gate_passes_clean_output(self):
        """Output with no markers returns (True, "ok")."""
        renderer = CLLMRenderer()
        mock_packet = TaggedResponsePacket(
            user_text="test", facts=[], constraints=[], tone="helpful", length_hint="short"
        )
        clean_response = "The file was saved successfully at 2:30 PM."
        passed, reason = renderer._gate_output(clean_response, mock_packet)
        assert passed is True
        assert reason == "ok"

    def test_gate_fails_on_hedge_marker(self):
        """'i think' triggers gate failure."""
        renderer = CLLMRenderer()
        mock_packet = TaggedResponsePacket(
            user_text="test", facts=[], constraints=[], tone="helpful", length_hint="short"
        )
        hedged_response = "I think the file was saved successfully."
        passed, reason = renderer._gate_output(hedged_response, mock_packet)
        assert passed is False
        assert "i think" in reason

    def test_gate_fails_on_escape_marker(self):
        """'based on my knowledge' triggers gate failure."""
        renderer = CLLMRenderer()
        mock_packet = TaggedResponsePacket(
            user_text="test", facts=[], constraints=[], tone="helpful", length_hint="short"
        )
        escape_response = "Based on my knowledge, the file should be saved."
        passed, reason = renderer._gate_output(escape_response, mock_packet)
        assert passed is False
        assert "scope_escape:" in reason

    def test_gate_fails_on_typically_marker(self):
        """'typically' triggers gate failure."""
        renderer = CLLMRenderer()
        mock_packet = TaggedResponsePacket(
            user_text="test", facts=[], constraints=[], tone="helpful", length_hint="short"
        )
        response = "Typically, files are saved in the documents folder."
        passed, reason = renderer._gate_output(response, mock_packet)
        assert passed is False
        assert "typically" in reason

    def test_gate_case_insensitive(self):
        """Gate detection is case insensitive."""
        renderer = CLLMRenderer()
        mock_packet = TaggedResponsePacket(
            user_text="test", facts=[], constraints=[], tone="helpful", length_hint="short"
        )
        response = "I THINK the file was saved."
        passed, reason = renderer._gate_output(response, mock_packet)
        assert passed is False


class TestRenderWithAnchoring:
    """Test render() method with fact anchoring."""

    def test_render_uses_anchored_prompt(self, monkeypatch):
        """Verify render() builds anchored prompt."""
        renderer = CLLMRenderer()
        captured_prompts = []

        def mock_run(prompt, keep_alive="2h"):
            captured_prompts.append(prompt)
            from unittest.mock import Mock
            mock = Mock()
            mock.ok = True
            mock.text = "Response"
            return mock

        # Mock environment to bypass PYTEST_CURRENT_TEST check
        monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)

        # Mock both preferred and fallback to capture prompts
        monkeypatch.setattr(renderer._preferred, "run", mock_run)
        monkeypatch.setattr(renderer._fallback, "run", mock_run)

        packet = TaggedResponsePacket(
            user_text="Test",
            facts=["tool:test fact"],
            constraints=[],
            tone="helpful",
            length_hint="short",
            tool_summaries=["test fact"],
            memory_items=[],
            job_snapshot=None,
        )
        renderer.render(packet)
        # Note: render() returns a dict now, but we're just checking that it ran and built prompts
        assert len(captured_prompts) > 0
        assert "PERMITTED FACTS" in captured_prompts[0]
        assert "[1] test fact" in captured_prompts[0]

    def test_render_falls_through_to_deterministic_on_double_gate_fail(self, monkeypatch):
        """Mock both Ollama calls to return hedged output; verify deterministic fallback fires."""
        renderer = CLLMRenderer()

        def mock_run(prompt, keep_alive="2h"):
            from unittest.mock import Mock
            mock = Mock()
            mock.ok = True
            mock.text = "I think this is the answer."
            return mock

        monkeypatch.setattr(renderer._preferred, "run", mock_run)
        monkeypatch.setattr(renderer._fallback, "run", mock_run)

        packet = TaggedResponsePacket(
            user_text="Test",
            facts=[],
            constraints=[],
            tone="helpful",
            length_hint="short",
            tool_summaries=[],
            memory_items=[],
            job_snapshot=None,
            deterministic_fallback="This is the deterministic fallback response.",
        )
        result_dict = renderer.render(packet)
        result = result_dict["text"]
        assert "deterministic fallback" in result.lower()


class TestScopeEscapeEvent:
    """Test renderer_scope_escape event emission."""

    def test_emit_scope_escape_event(self, tmp_path, monkeypatch):
        """Verify event is emitted on gate failure."""
        log_dir = tmp_path / "logs"
        log_dir.mkdir()
        renderer = CLLMRenderer(log_dir=str(log_dir))

        packet = TaggedResponsePacket(
            user_text="Test",
            facts=[],
            constraints=[],
            tone="helpful",
            length_hint="short",
            tool_summaries=[],
            memory_items=[],
            job_snapshot=None,
        )

        # Call internal method directly to test event emission
        renderer._emit_scope_escape(packet, "scope_escape:i think", "preferred")

        # Check that event was written to log
        import os
        from datetime import datetime, timezone
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        log_file = log_dir / f"jarvis_events_{today}.jsonl"
        assert log_file.exists()
        content = log_file.read_text()
        assert "renderer_scope_escape" in content
        assert "scope_escape:i think" in content


class TestLLMPathBypass:
    """Test LLM path by bypassing PYTEST_CURRENT_TEST. (P3-2)"""

    def test_render_gates_hedged_llm_output(self, monkeypatch):
        """Verify that when LLM path is enabled, hedged output is still gated."""
        renderer = CLLMRenderer()
        
        # Mock environment to bypass PYTEST_CURRENT_TEST check
        monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)
        
        # Mock Ollama to return a response with a hedge marker
        class MockResult:
            def __init__(self, text):
                self.text = text
                self.ok = True
        
        def mock_run(prompt, **kwargs):
            return MockResult("I think the answer is 42.")
            
        monkeypatch.setattr(renderer._preferred, "run", mock_run)
        monkeypatch.setattr(renderer._fallback, "run", mock_run)
        
        packet = TaggedResponsePacket(
            user_text="What is the answer?",
            facts=[],
            constraints=[],
            tone="helpful",
            length_hint="short",
            deterministic_fallback="Deterministic fallback.",
        )
        
        result_dict = renderer.render(packet)
        result = result_dict["text"]
        
        # Should NOT be the hedged LLM output, but the fallback
        assert "I think" not in result
        assert result == "Deterministic fallback."

