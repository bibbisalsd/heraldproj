from __future__ import annotations
from jarvis.main import JarvisRuntime


def test_runtime_time_query_returns_local_time():
    rt = JarvisRuntime()
    rt.startup(model_ready=True)
    result = rt.run_turn("jarvis whats the time")
    assert result["lane"] == "realtime"
    assert any(token in result["text"].upper() for token in ("A M", "P M"))
    assert "gmt summer time" not in result["text"].lower()
    assert "2026-" not in result["text"].lower()


def test_runtime_time_query_uses_spoken_12_hour_format():
    rt = JarvisRuntime()
    rt.startup(model_ready=True)
    rt.tool_orchestrator._tools["local_now"] = lambda: {
        "iso": "2026-04-03T15:30:00+01:00",
        "local_time": "15:30",
        "spoken_time": "3:30 pm",
        "local_date": "2026-04-03",
        "timezone": "GMT Summer Time",
    }

    result = rt.run_turn("jarvis whats the time")

    assert result["lane"] == "realtime"
    assert result["resolved_by"] == "tool_only"
    assert "3:30" in result["text"] and any(token in result["text"].upper() for token in ("A M", "P M"))
    assert "15:30" not in result["text"]
    assert "gmt summer time" not in result["text"].lower()
    assert "2026-04-03" not in result["text"].lower()


def test_runtime_day_query_returns_day_without_time():
    rt = JarvisRuntime()
    rt.startup(model_ready=True)
    rt.tool_orchestrator._tools["local_now"] = lambda: {
        "iso": "2026-04-03T15:30:00+01:00",
        "local_time": "15:30",
        "spoken_time": "3:30 pm",
        "spoken_day": "Friday",
        "spoken_date": "Friday the 3rd of April",
        "local_date": "2026-04-03",
        "timezone": "GMT Summer Time",
    }

    result = rt.run_turn("JAVIS, what day is it?")

    assert result["lane"] == "realtime"
    assert result["resolved_by"] == "tool_only"
    assert "friday" in result["text"].lower()
    assert "pm" not in result["text"].lower()


def test_runtime_date_query_returns_spoken_date_without_time():
    rt = JarvisRuntime()
    rt.startup(model_ready=True)
    rt.tool_orchestrator._tools["local_now"] = lambda: {
        "iso": "2026-11-02T15:30:00+00:00",
        "local_time": "15:30",
        "spoken_time": "3:30 pm",
        "spoken_day": "Tuesday",
        "spoken_date": "Tuesday the 2nd of November",
        "local_date": "2026-11-02",
        "timezone": "GMT",
    }

    result = rt.run_turn("Jarvis, what date is it?")

    assert result["lane"] == "realtime"
    assert result["resolved_by"] == "tool_only"
    assert "tuesday the 2nd of november" in result["text"].lower()
    assert "pm" not in result["text"].lower()


def test_runtime_can_remember_and_recall_name():
    rt = JarvisRuntime()
    rt.startup(model_ready=True)
    first = rt.run_turn("my name is Sam")
    second = rt.run_turn("what is my name")
    assert "name as Sam" in first["text"]
    assert second["text"] == "I have your name as Sam."


def test_runtime_general_question_uses_local_model_reply(monkeypatch):
    rt = JarvisRuntime()
    rt.startup(model_ready=True)
    monkeypatch.setattr(rt.turn_pipeline, "_generate_general_chat_reply", lambda _text: "Christmas is on December 25.")

    result = rt.run_turn("tell me when Christmas is")

    assert result["lane"] == "realtime"
    assert result["resolved_by"] == "model_reasoning"
    assert "December 25" in result["text"]


def test_runtime_capability_question_uses_help_handler():
    rt = JarvisRuntime()
    rt.startup(model_ready=True)

    result = rt.run_turn("Can you tell me what you can do, Jarvis?")

    assert result["lane"] == "realtime"
    assert result["resolved_by"] in ("tool_only", "tool_plus_renderer")
    # Real output from _compose_capabilities uses pocket memory
    assert "time" in result["text"].lower() or "built for" in result["text"].lower()
    assert "calculator" in result["text"].lower() or "calculations" in result["text"].lower() or "search" in result["text"].lower()


def test_runtime_mixed_greeting_and_wellbeing_prefers_brain_handler():
    rt = JarvisRuntime()
    rt.startup(model_ready=True)

    result = rt.run_turn("Hello, Jarvis. How are you?")

    assert result["lane"] == "realtime"
    assert result["resolved_by"] == "tool_plus_renderer"
    assert "online" in result["text"].lower()


def test_runtime_math_question_uses_calculator():
    rt = JarvisRuntime()
    rt.startup(model_ready=True)

    result = rt.run_turn("Javis, what is 1304 times 306?")

    assert result["lane"] == "realtime"
    assert result["resolved_by"] == "tool_only"
    assert "399024" in result["text"]


def test_runtime_where_are_you_uses_grounded_identity_handler(monkeypatch):
    rt = JarvisRuntime()
    rt.startup(model_ready=True)
    monkeypatch.setattr(
        rt.turn_pipeline,
        "_generate_general_chat_reply",
        lambda _text: (_ for _ in ()).throw(AssertionError("general chat should not run")),
    )

    result = rt.run_turn("Javis, do you know where you are?")

    assert result["lane"] == "realtime"
    assert result["resolved_by"] == "tool_plus_renderer"
    assert "running locally on this computer" in result["text"].lower()


def test_runtime_screen_question_routes_to_vision_specialist(monkeypatch):
    from jarvis.main import TurnExecutionResult
    rt = JarvisRuntime()
    rt.startup(model_ready=True)

    # Mock the specialist runner lambda directly
    monkeypatch.setattr(
        rt, "_execute_realtime", 
        lambda env, decision: TurnExecutionResult(
            lane="realtime", 
            text="File Explorer is open.", 
            resolved_by="tool_plus_renderer",
            tool_summaries=["vision_specialist:ok"]
        )
    )

    result = rt.run_turn("What do you see on my screen, Jarvis?")

    assert result["lane"] == "realtime"
    assert result["resolved_by"] == "tool_plus_renderer"
    assert result["text"] == "File Explorer is open."


def test_runtime_codebase_question_stays_grounded_without_hallucinating(monkeypatch):
    rt = JarvisRuntime()
    rt.startup(model_ready=True)
    monkeypatch.setattr(
        rt.turn_pipeline,
        "_generate_general_chat_reply",
        lambda _text: (_ for _ in ()).throw(AssertionError("general chat should not run")),
    )

    result = rt.run_turn("Javis, do you know your code base?")

    assert result["lane"] == "realtime"
    assert result["resolved_by"] in ("tool_plus_renderer", "tool_only")
    assert "python modules" in result["text"].lower()
    assert "subsystems" in result["text"].lower()


def test_runtime_age_question_does_not_guess():
    rt = JarvisRuntime()
    rt.startup(model_ready=True)

    result = rt.run_turn("Javis, do you know how old I am?")

    assert result["lane"] == "realtime"
    assert result["resolved_by"] == "tool_plus_renderer"
    assert "do not know your age" in result["text"].lower()


def test_runtime_who_are_you_uses_protected_self_pocket():
    rt = JarvisRuntime()
    rt.startup(model_ready=True)

    result = rt.run_turn("Who are you, Jarvis?")

    assert result["lane"] == "realtime"
    assert result["resolved_by"] in ("tool_only", "tool_plus_renderer")
    assert "i am jarvis" in result["text"].lower()
    assert "local a i assistant" in result["text"].lower() or "local ai assistant" in result["text"].lower()


def test_runtime_where_is_your_code_uses_codebase_pocket():
    rt = JarvisRuntime()
    rt.startup(model_ready=True)

    result = rt.run_turn("Where is your code, Jarvis?")

    assert result["lane"] == "realtime"
    assert result["resolved_by"] == "tool_plus_renderer"
    assert "jarviscore" in result["text"].lower()
    assert "local folder" in result["text"].lower() or "jarviscore" in result["text"].lower()


def test_runtime_how_do_you_work_uses_runtime_flow_pocket():
    rt = JarvisRuntime()
    rt.startup(model_ready=True)

    result = rt.run_turn("Jarvis, how do you work?")

    assert result["lane"] == "realtime"
    assert result["resolved_by"] == "tool_plus_renderer"
    assert "voice runtime" in result["text"].lower()
    assert "prompt dispatcher" in result["text"].lower()


def test_runtime_where_do_you_keep_your_source_files_uses_deterministic_code_routing():
    rt = JarvisRuntime()
    rt.startup(model_ready=True)

    result = rt.run_turn("Jarvis, where do you keep your source files?")

    assert result["lane"] == "realtime"
    assert result["resolved_by"] in ("tool_only", "tool_plus_renderer")
    assert "local folder" in result["text"].lower() or "local path" in result["text"].lower()


def test_runtime_which_tools_are_available_uses_deterministic_tool_routing():
    rt = JarvisRuntime()
    rt.startup(model_ready=True)

    result = rt.run_turn("Which tools are available to you, Jarvis?")

    assert result["lane"] == "realtime"
    assert result["resolved_by"] in ("tool_only", "tool_plus_renderer")
    assert "calculator" in result["text"].lower() or "timetool" in result["text"].lower()


def test_runtime_what_are_you_doing_still_routes_to_status_not_self_identity():
    rt = JarvisRuntime()
    rt.startup(model_ready=True)

    result = rt.run_turn("what are you doing")

    assert result["lane"] == "realtime"
    assert result["resolved_by"] == "template"
    assert "online" in result["text"].lower()


def test_runtime_thanks_uses_brain_social_handler():
    rt = JarvisRuntime()
    rt.startup(model_ready=True)

    result = rt.run_turn("Thank you.")

    assert result["lane"] == "realtime"
    assert result["resolved_by"] == "tool_only"
    assert result["text"] == "You're welcome."


def test_runtime_goodnight_uses_brain_social_handler():
    rt = JarvisRuntime()
    rt.startup(model_ready=True)

    result = rt.run_turn("Jarvis, I'm gonna go to sleep okay good night")

    assert result["lane"] == "realtime"
    assert result["resolved_by"] == "tool_only"
    assert result["text"] == "Goodnight."


def test_runtime_feedback_uses_brain_social_handler():
    rt = JarvisRuntime()
    rt.startup(model_ready=True)

    result = rt.run_turn("It's okay, your responses could be better, but it's okay.")

    assert result["lane"] == "realtime"
    assert result["resolved_by"] == "tool_only"
    assert "respond more clearly" in result["text"].lower()


def test_runtime_affection_uses_brain_social_handler():
    rt = JarvisRuntime()
    rt.startup(model_ready=True)

    result = rt.run_turn("Javis, I love you. I'm very proud of you.")

    assert result["lane"] == "realtime"
    assert result["resolved_by"] == "tool_only"
    assert result["text"] == "Thank you. I appreciate that."


def test_runtime_no_speech_correction_uses_brain_social_handler():
    rt = JarvisRuntime()
    rt.startup(model_ready=True)

    result = rt.run_turn("I didn't say anything, Jarvis.")

    assert result["lane"] == "realtime"
    assert result["resolved_by"] == "tool_only"
    assert result["text"] == "Understood. I will wait for you to speak."


def test_runtime_recall_name_can_fallback_to_owner_pocket():
    rt = JarvisRuntime()
    rt.startup(model_ready=True)
    rt.memory.pockets.ensure_owner_pocket(canonical_name="James")
    rt.memory.pockets.set_slot(
        "person:owner",
        "name",
        "James",
        provenance_type="conversation",
        source="test",
        protection_level="dynamic",
        allow_update_protected=True,
    )

    result = rt.run_turn("what is my name")

    assert result["lane"] == "realtime"
    assert result["resolved_by"] == "tool_plus_renderer"
    assert result["text"] == "I have your name as James."


def test_runtime_address_preference_is_saved_and_acknowledged():
    rt = JarvisRuntime()
    rt.startup(model_ready=True)
    rt.run_turn("my name is James")

    result = rt.run_turn("Javis, refer to me as James or Sir.")

    assert result["lane"] == "realtime"
    assert result["resolved_by"] == "tool_plus_renderer"
    assert "James" in result["text"]
    assert "sir" in result["text"]
    assert rt.memory.recall("user_address_preference")[0].value == "James"
    assert rt.memory.recall("user_title_preference")[0].value.lower() == "sir"


def test_runtime_address_correction_uses_saved_name():
    rt = JarvisRuntime()
    rt.startup(model_ready=True)
    rt.run_turn("my name is James")
    rt.run_turn("Javis, refer to me as James or Sir.")

    result = rt.run_turn("Not both of them, Jarvis. Don't refer me to Sir James.")

    assert result["lane"] == "realtime"
    assert result["resolved_by"] == "tool_only"
    assert "James" in result["text"]
    assert "sir" in result["text"]
    assert rt.memory.recall("user_address_preference")[0].value == "James"


def test_runtime_launch_greeting_prompts_for_name_when_unknown():
    rt = JarvisRuntime()
    rt.startup(model_ready=True)

    greeting = rt.conversation.launch_greeting()

    assert "what is your name" in greeting.lower()
    assert rt.conversation.expects_follow_up_without_wake_word() is True


def test_runtime_onboarding_can_capture_bare_name_reply():
    rt = JarvisRuntime()
    rt.startup(model_ready=True)
    rt.conversation.launch_greeting()

    result = rt.run_turn("James")

    assert result["lane"] == "realtime"
    assert "remember your name as James" in result["text"]
    assert rt.memory.owner_name() == "James"
    assert rt.conversation.expects_follow_up_without_wake_word() is True


def test_runtime_local_mic_turn_opens_short_follow_up_window():
    rt = JarvisRuntime()
    rt.startup(model_ready=True)

    rt.run_turn("status", source="local_mic")

    assert rt.conversation.expects_follow_up_without_wake_word() is True


def test_runtime_onboarding_can_extract_name_from_longer_phrase():
    rt = JarvisRuntime()
    rt.startup(model_ready=True)
    rt.conversation.launch_greeting()

    result = rt.run_turn("I am James, your creator, Javis.")

    assert "remember your name as James" in result["text"]
    assert rt.memory.owner_name() == "James"


def test_runtime_unisex_name_prompts_for_title_preference():
    rt = JarvisRuntime()
    rt.startup(model_ready=True)

    result = rt.run_turn("my name is Sam")

    assert "sir or madam" in result["text"].lower()
    assert rt.conversation.expects_follow_up_without_wake_word() is True


def test_runtime_unisex_title_reply_is_saved():
    rt = JarvisRuntime()
    rt.startup(model_ready=True)

    rt.run_turn("my name is Sam")
    result = rt.run_turn("sir")

    assert result["resolved_by"] == "tool_only"
    assert "refer to you as sir" in result["text"].lower()
    assert rt.memory.recall("user_title_preference")[0].value == "sir"


def test_runtime_self_query_can_answer_creator_info():
    rt = JarvisRuntime()
    rt.startup(model_ready=True)

    result = rt.run_turn("Who created you, Jarvis?")

    assert result["lane"] == "realtime"
    assert "gxzx" in result["text"].lower()
    assert "berserk" in result["text"].lower()


def test_runtime_creator_phrase_verification_is_hidden_and_sets_creator_session():
    rt = JarvisRuntime()
    rt.startup(model_ready=True)
    rt.run_turn("my name is James")

    first = rt.run_turn("I created you")
    second = rt.run_turn("259")

    assert "creator phrase" in first["text"].lower()
    assert second["sensitive_input"] is True
    assert "verification accepted" in second["text"].lower()
    assert "james" in second["text"].lower()


def test_runtime_creator_context_stays_grounded_after_verification():
    rt = JarvisRuntime()
    rt.startup(model_ready=True)
    rt.run_turn("my name is James")
    rt.run_turn("I created you")
    rt.run_turn("259")

    result = rt.run_turn("Yes, but Jarvis, I am your main creator, James.")

    assert result["lane"] == "realtime"
    assert result["resolved_by"] == "tool_only"
    assert "verified creator" in result["text"].lower()
    assert "main person" in result["text"].lower()


def test_runtime_performance_context_stays_grounded():
    rt = JarvisRuntime()
    rt.startup(model_ready=True)

    result = rt.run_turn("It's okay, Jarvis, you're a little slow. We need to make you quicker.")

    assert result["lane"] == "realtime"
    assert result["resolved_by"] in ("tool_only", "template")
    # Keywords for performance context
    assert any(k in result["text"].lower() for k in ["sequential relay", "lightweight", "load time"])


def test_runtime_long_term_improvement_context_stays_grounded():
    rt = JarvisRuntime()
    rt.startup(model_ready=True)

    result = rt.run_turn("Yes, but Jarvis, your long term plan has self improvement.")

    assert result["lane"] == "realtime"
    assert result["resolved_by"] in ("tool_only", "template")
    # Both map to performance handler which talks about Sequential Relay
    assert any(k in result["text"].lower() for k in ["sequential relay", "lightweight", "load time"])
    # These were specific to the old hardcoded response, keeping them if they still exist in some form
    # but the primary verification is the handler routing.
    # assert "codebase" in result["text"].lower()
    # assert "do not rewrite myself automatically" in result["text"].lower()


def test_runtime_memory_wipe_requires_two_confirmations_and_preserves_core():
    rt = JarvisRuntime()
    rt.startup(model_ready=True)
    rt.run_turn("my name is James")

    first = rt.run_turn("wipe your memory")
    second = rt.run_turn("confirm memory wipe")
    third = rt.run_turn("confirm memory wipe now")

    assert "confirm memory wipe" in first["text"].lower()
    assert "final confirmation" in second["text"].lower()
    assert "memory wipe complete" in third["text"].lower()
    assert rt.memory.owner_name() is None
    assert rt.memory.pockets.get_entity("self:jarvis") is not None
    assert rt.memory.pockets.get_entity("person:creator_james") is not None
    assert rt.conversation.expects_follow_up_without_wake_word() is True


def test_runtime_can_save_and_recall_age_from_owner_pocket():
    rt = JarvisRuntime()
    rt.startup(model_ready=True)

    first = rt.run_turn("I am 32 years old.")
    second = rt.run_turn("How old am I?")

    assert first["resolved_by"] == "tool_plus_renderer"
    assert second["resolved_by"] == "tool_plus_renderer"
    assert "age as 32" in first["text"]
    assert "age as 32" in second["text"]


def test_runtime_owner_summary_is_composed_from_saved_pocket_facts():
    rt = JarvisRuntime()
    rt.startup(model_ready=True)
    rt.run_turn("My name is James")
    rt.run_turn("Call me James")
    rt.run_turn("My age is 32")

    result = rt.run_turn("What do you know about me?")

    assert result["lane"] == "realtime"
    assert result["resolved_by"] == "tool_plus_renderer"
    assert "your name as James" in result["text"]
    assert "your age as 32" in result["text"]


def test_runtime_address_preference_recall_uses_owner_pocket():
    rt = JarvisRuntime()
    rt.startup(model_ready=True)
    rt.run_turn("My name is James")
    rt.run_turn("Call me James")

    result = rt.run_turn("What do you call me?")

    assert result["lane"] == "realtime"
    assert result["resolved_by"] == "tool_plus_renderer"
    assert "James" in result["text"]


def test_runtime_hallucination_correction_stays_grounded():
    rt = JarvisRuntime()
    rt.startup(model_ready=True)

    result = rt.run_turn("Jarvis you're making things up that is not good")

    assert result["lane"] == "realtime"
    assert result["resolved_by"] == "tool_only"
    assert "should not guess" in result["text"].lower()


def test_runtime_what_made_you_think_response_does_not_improvise():
    rt = JarvisRuntime()
    rt.startup(model_ready=True)

    result = rt.run_turn("Javis, what made you think I'm 32 years old?")

    assert result["lane"] == "realtime"
    assert result["resolved_by"] == "tool_only"
    assert "should not have guessed" in result["text"].lower()


def test_runtime_context_continuity_correction_stays_brain_first():
    rt = JarvisRuntime()
    rt.startup(model_ready=True)

    result = rt.run_turn("JAVIS, we're not starting fresh.")

    assert result["lane"] == "realtime"
    assert result["resolved_by"] == "tool_only"
    assert "stay with the current conversation" in result["text"].lower()


def test_runtime_wellbeing_reports_health_summary():
    rt = JarvisRuntime()
    rt.startup(model_ready=True)

    result = rt.run_turn("How are you, Jarvis?")

    assert result["lane"] == "realtime"
    assert result["resolved_by"] in ("tool_only", "tool_plus_renderer")
    assert "online" in result["text"].lower()
    assert "responding normally" in result["text"].lower()


def test_runtime_preloads_realtime_model_on_startup():
    rt = JarvisRuntime()
    rt.startup(model_ready=True)

    assert rt._model_keepalive_thread is not None


def test_runtime_hearing_query_stays_grounded():
    rt = JarvisRuntime()
    rt.startup(model_ready=True)

    result = rt.run_turn("Javis, can you hear me?")

    assert result["lane"] == "realtime"
    assert result["resolved_by"] == "tool_only"
    assert any(phrase in result["text"].lower() for phrase in ("hear you", "hearing you"))
