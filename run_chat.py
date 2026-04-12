from jarvis.main import JarvisRuntime
import os
import threading
import time
import sys

# Ensure Kokoro pack is found if enabled
os.environ.setdefault("JARVIS_KOKORO_PACK_DIR",
    os.path.join(os.path.dirname(os.path.abspath(__file__)),
                 "jarvis", "voice", "kokoro_pack"))

# ANSI escape codes
DIM = "\033[2m"
CYAN = "\033[36m"
RESET = "\033[0m"
CLEAR_LINE = "\r\033[K"

rt = JarvisRuntime()
print("Warming up models (Sequential Relay)...", end="", flush=True)
# startup() preloads the embedding and renderer models into VRAM
rt.startup(model_ready=True)
print(" Ready.")

print("Jarvis started (Text + Voice Mode). Type 'exit' to quit.")

def bg1_progress_monitor():
    """Async terminal display: streams BG1 thinking/tokens and stage updates."""
    last_stage = ""
    inside_think = False
    was_streaming = False
    stream_header_printed = False

    while True:
        mgr = rt.bg1_manager

        # Priority 1: Stream tokens from the LLM if active
        if mgr._stream_active or mgr._stream_read_pos < len(mgr._stream_tokens):
            new_tokens = mgr.read_new_stream_tokens()
            if new_tokens:
                for token in new_tokens:
                    # Detect <think> tags for deepseek-r1 thinking display
                    if "<think>" in token:
                        inside_think = True
                        if not stream_header_printed:
                            sys.stdout.write(f"\n{DIM}{CYAN}[BG1 thinking]{RESET}{DIM} ")
                            stream_header_printed = True
                        token = token.replace("<think>", "")
                    if "</think>" in token:
                        inside_think = False
                        token = token.replace("</think>", "")
                        sys.stdout.write(f"{RESET}\n{CYAN}[BG1]{RESET} ")

                    if inside_think:
                        sys.stdout.write(f"{DIM}{token}{RESET}")
                    elif not stream_header_printed:
                        # No <think> tag — model is responding directly
                        if not was_streaming:
                            sys.stdout.write(f"\n{CYAN}[BG1]{RESET} ")
                        sys.stdout.write(token)
                    else:
                        sys.stdout.write(token)
                    sys.stdout.flush()
                was_streaming = True
            time.sleep(0.05)  # Fast poll for smooth streaming
            continue

        # Streaming just ended — print newline and redraw prompt
        if was_streaming:
            sys.stdout.write(f"{RESET}\n")
            sys.stdout.flush()
            was_streaming = False
            inside_think = False
            stream_header_printed = False
            last_stage = ""

        # Priority 2: Stage-based progress updates
        current = rt.job_status.get_current()
        if current and current.state not in ("completed", "COMPLETED", "failed", "IDLE"):
            if current.stage != last_stage:
                sys.stdout.write(f"{CLEAR_LINE}{CYAN}[BG1]{RESET} {current.stage}\nYou> ")
                sys.stdout.flush()
                last_stage = current.stage
        else:
            last_stage = ""

        time.sleep(0.3)

# Start background monitor thread
monitor_thread = threading.Thread(target=bg1_progress_monitor, daemon=True)
monitor_thread.start()

while True:
    try:
        user = input("You> ").strip()
    except EOFError:
        break
    if not user:
        continue
    if user.lower() in {"exit", "quit"}:
        break

    result = rt.run_turn(user)

    if os.environ.get("JARVIS_DEBUG") == "1":
        print(f"\n{CYAN}--- DEBUG TRACE ---{RESET}")
        print(f"{DIM}Routing: {result.get('match_type')} -> {result.get('lane')} ({result.get('route_reason')}){RESET}")
        print(f"{DIM}Intent:  {result.get('intent')} (resolved_by: {result.get('resolved_by')}){RESET}")
        
        if result.get("llm_model") and result.get("llm_model") != "none":
            print(f"{DIM}Model:   {result.get('llm_model')} ({result.get('llm_elapsed_ms', 0):.1f}ms){RESET}")
        
        tools = result.get("tool_summaries", [])
        tool_results = result.get("tool_results", [])
        if tools:
            print(f"{DIM}Tools:   {', '.join(tools)}{RESET}")
            for i, res in enumerate(tool_results):
                name = getattr(res, 'tool_name', f"tool_{i}")
                summary = getattr(res, 'summary', str(res))
                print(f"{DIM}  - {name}: {summary}{RESET}")
        
        packet = result.get("evidence_packet")
        if packet:
            facts = getattr(packet, "verified_facts", [])
            if facts:
                print(f"{DIM}Fact Packet ({len(facts)}):{RESET}")
                for f in facts:
                    strength = getattr(f, "verification_strength", "unknown")
                    content = getattr(f, "content", str(f))
                    print(f"{DIM}  - [{strength}] {content}{RESET}")
        
        raw_output = result.get("raw_llm_output")
        if raw_output:
            print(f"{DIM}Raw LLM: {raw_output}{RESET}")

        memory = result.get("memory_items", [])
        if memory:
            print(f"{DIM}Memory:  {len(memory)} hits{RESET}")
        print(f"{CYAN}-------------------{RESET}\n")

    # Prefer display_text (full result) over text (voice-truncated)
    display = result.get("display_text") or result["text"]
    print(f"Jarvis> {display}")

rt.shutdown()
