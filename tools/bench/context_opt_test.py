#!/usr/bin/env python3
"""
Context optimization A/B tests for non-thinking gemma4 (31B) agent.

Tests:
1. Skip skill context on retry
2. Review feedback position (before vs after skill context)
3. Latest-only vs all-attempts feedback
4. Remove RECAP messages

Each test: 5 baseline replays + 5 optimized replays.
"""

import json
import re
import time
import copy
import sys
import requests

GATEWAY = "http://localhost:11000/v1/chat/completions"
MODEL = "gemma4"
MAX_TOKENS = 2000
TIMEOUT = 300
REPS = 5

CAM_FILE = "/home/u0/Work/scifi/Cam/driver_fw_complete2_20260517223428.jsonl"


def load_events():
    with open(CAM_FILE) as f:
        return [json.loads(line) for line in f]


def parse_msgs_tools(ev):
    msgs = json.loads(ev["messages"]) if isinstance(ev["messages"], str) else ev["messages"]
    tools = json.loads(ev["tools"]) if isinstance(ev["tools"], str) else ev["tools"]
    return msgs, tools


def send_request(msgs, tools, label=""):
    payload = {
        "model": MODEL,
        "messages": msgs,
        "tools": tools,
        "max_tokens": MAX_TOKENS,
    }
    t0 = time.time()
    try:
        resp = requests.post(GATEWAY, json=payload, timeout=TIMEOUT)
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        return {"error": str(e), "latency": time.time() - t0}

    latency = time.time() - t0
    choice = data["choices"][0]
    msg = choice["message"]

    result = {
        "latency": round(latency, 2),
        "prompt_tokens": data.get("usage", {}).get("prompt_tokens", 0),
        "completion_tokens": data.get("usage", {}).get("completion_tokens", 0),
        "content": msg.get("content", ""),
        "tool_calls": [],
        "shift_reg_line": None,
    }

    if msg.get("tool_calls"):
        for tc in msg["tool_calls"]:
            fn = tc.get("function", {})
            name = fn.get("name", "?")
            args_str = fn.get("arguments", "{}")
            try:
                args = json.loads(args_str) if isinstance(args_str, str) else args_str
            except json.JSONDecodeError:
                args = {"_raw": args_str}
            result["tool_calls"].append({"name": name, "args_keys": list(args.keys())})

            # Check for write_file to stream_wrapper.v with shift_reg
            if name == "write_file":
                content = args.get("content", "")
                for line in content.split("\n"):
                    if "shift_reg" in line and "<=" in line:
                        result["shift_reg_line"] = line.strip()
                        break

    return result


def print_result(r, idx):
    if "error" in r:
        print(f"  [{idx}] ERROR: {r['error']} ({r['latency']:.1f}s)")
        return
    first_tool = r["tool_calls"][0]["name"] if r["tool_calls"] else "(text-only)"
    sr = f" shift_reg: {r['shift_reg_line']}" if r["shift_reg_line"] else ""
    print(
        f"  [{idx}] {r['latency']:6.1f}s | "
        f"pt={r['prompt_tokens']:5d} ct={r['completion_tokens']:4d} | "
        f"first_tool={first_tool}{sr}"
    )
    if r["content"]:
        print(f"         text: {r['content'][:120]}")


def run_ab(label_a, msgs_a, tools_a, label_b, msgs_b, tools_b):
    print(f"\n  --- {label_a} (baseline) ---")
    results_a = []
    for i in range(REPS):
        r = send_request(msgs_a, tools_a, label_a)
        print_result(r, i + 1)
        results_a.append(r)

    print(f"\n  --- {label_b} (optimized) ---")
    results_b = []
    for i in range(REPS):
        r = send_request(msgs_b, tools_b, label_b)
        print_result(r, i + 1)
        results_b.append(r)

    return results_a, results_b


def summarize(results_a, results_b, label_a, label_b):
    def stats(results):
        valid = [r for r in results if "error" not in r]
        if not valid:
            return {"avg_latency": 0, "avg_pt": 0, "avg_ct": 0, "tools": [], "shift_regs": []}
        return {
            "avg_latency": sum(r["latency"] for r in valid) / len(valid),
            "avg_pt": sum(r["prompt_tokens"] for r in valid) / len(valid),
            "avg_ct": sum(r["completion_tokens"] for r in valid) / len(valid),
            "tools": [r["tool_calls"][0]["name"] if r["tool_calls"] else "(text)" for r in valid],
            "shift_regs": [r["shift_reg_line"] for r in valid if r["shift_reg_line"]],
        }

    sa = stats(results_a)
    sb = stats(results_b)

    print(f"\n  Summary:")
    print(f"    {label_a}: avg latency={sa['avg_latency']:.1f}s, avg pt={sa['avg_pt']:.0f}, avg ct={sa['avg_ct']:.0f}")
    print(f"      first tools: {sa['tools']}")
    if sa["shift_regs"]:
        print(f"      shift_regs: {sa['shift_regs']}")
    print(f"    {label_b}: avg latency={sb['avg_latency']:.1f}s, avg pt={sb['avg_pt']:.0f}, avg ct={sb['avg_ct']:.0f}")
    print(f"      first tools: {sb['tools']}")
    if sb["shift_regs"]:
        print(f"      shift_regs: {sb['shift_regs']}")

    pt_saved = sa["avg_pt"] - sb["avg_pt"]
    latency_diff = sb["avg_latency"] - sa["avg_latency"]
    print(f"    Token delta: {pt_saved:+.0f} prompt tokens ({'-' if pt_saved > 0 else '+'}{abs(pt_saved)/max(sa['avg_pt'],1)*100:.1f}%)")
    print(f"    Latency delta: {latency_diff:+.1f}s")


# ============================================================
# TEST 1: Skip skill context on retry
# ============================================================
def test1(events):
    print("\n" + "=" * 70)
    print("TEST 1: Skip skill context on retry")
    print("=" * 70)
    print("Source: SAM at line 521 (worker retry with 2 prior attempts + skill context)")

    ev = events[521]
    msgs, tools = parse_msgs_tools(ev)

    # Baseline: original
    msgs_a = copy.deepcopy(msgs)

    # Optimized: remove skill context section from msgs[1]
    msgs_b = copy.deepcopy(msgs)
    content = msgs_b[1]["content"]

    # Skill context is between first --- (pos 1298) and second --- (pos 5322)
    # Find them precisely
    dash_positions = [m.start() for m in re.finditer(r"^---$", content, re.MULTILINE)]
    if len(dash_positions) >= 2:
        skill_start = dash_positions[0]  # first ---
        skill_end = dash_positions[1] + 3  # end of second ---
        content_opt = content[:skill_start] + content[skill_end:]
        msgs_b[1]["content"] = content_opt
        print(f"  Original content len: {len(content)}, Optimized: {len(content_opt)}")
        print(f"  Removed {len(content) - len(content_opt)} chars of skill context")
    else:
        print("  WARNING: Could not find skill section boundaries!")

    results_a, results_b = run_ab("A-with-skill", msgs_a, tools, "B-no-skill", msgs_b, tools)
    summarize(results_a, results_b, "A-with-skill", "B-no-skill")


# ============================================================
# TEST 2: Review feedback position
# ============================================================
def test2(events):
    print("\n" + "=" * 70)
    print("TEST 2: Review feedback position (after skill vs after task spec)")
    print("=" * 70)
    # SAM 3 at line 281 - early retry, feedback at bottom after skill
    # Also line 210 has same structure - let's use 210 (SAM 3 = index 2 of SAM_STARTs, first api at 210)
    # Actually line 281 has 2 attempts and skill=True too, let's use it
    ev = events[281]
    msgs, tools = parse_msgs_tools(ev)
    content = msgs[1]["content"]

    print(f"Source: line 281, content len={len(content)}")

    # Identify sections by --- boundaries
    dash_positions = [m.start() for m in re.finditer(r"^---$", content, re.MULTILINE)]
    print(f"  --- positions: {dash_positions}")

    # Sections:
    # 0 to dash[0]: task spec (## Context, ## Todo, ## Expect)
    # dash[0] to dash[1]: skill context
    # dash[1] to dash[2]: review feedback
    # dash[2] to end: env hints

    if len(dash_positions) >= 3:
        task_spec = content[: dash_positions[0]]
        skill_ctx = content[dash_positions[0] : dash_positions[1]]
        review_fb = content[dash_positions[1] : dash_positions[2]]
        env_hints = content[dash_positions[2] :]

        # Baseline A: original order (task, skill, review, hints)
        msgs_a = copy.deepcopy(msgs)

        # Optimized B: reorder to (task, review, skill, hints) - feedback right after task
        msgs_b = copy.deepcopy(msgs)
        content_opt = task_spec + review_fb + skill_ctx + env_hints
        msgs_b[1]["content"] = content_opt

        print(f"  Task spec: {len(task_spec)} chars")
        print(f"  Skill ctx: {len(skill_ctx)} chars")
        print(f"  Review fb: {len(review_fb)} chars")
        print(f"  Env hints: {len(env_hints)} chars")
        print(f"  Reordered: feedback moved from position {dash_positions[1]} to {len(task_spec)}")

        results_a, results_b = run_ab(
            "A-feedback-bottom", msgs_a, tools, "B-feedback-after-task", msgs_b, tools
        )
        summarize(results_a, results_b, "A-feedback-bottom", "B-feedback-after-task")
    else:
        print("  ERROR: Could not find 3 --- boundaries!")


# ============================================================
# TEST 3: Latest-only vs all-attempts feedback
# ============================================================
def test3(events):
    print("\n" + "=" * 70)
    print("TEST 3: Latest-only vs all-attempts feedback")
    print("=" * 70)

    # Use a review SAM with 5 attempts: line 511
    ev = events[511]
    msgs, tools = parse_msgs_tools(ev)
    content = msgs[1]["content"]

    print(f"Source: line 511 (review SAM, 5 accumulated attempts), content len={len(content)}")

    # Find all ## Attempt N blocks
    attempt_matches = list(re.finditer(r"## Attempt \d+", content))
    print(f"  Found {len(attempt_matches)} attempt blocks:")
    for a in attempt_matches:
        print(f"    {a.group()} at pos {a.start()}")

    if len(attempt_matches) >= 2:
        # Baseline A: all attempts (original)
        msgs_a = copy.deepcopy(msgs)

        # Optimized B: only the last attempt
        msgs_b = copy.deepcopy(msgs)
        last_attempt_start = attempt_matches[-1].start()
        # The review section starts after the transcript header
        # Find where the PRIOR REVIEW CONCLUSIONS section starts
        review_header = content.find("== PRIOR REVIEW CONCLUSIONS ==")
        if review_header >= 0:
            # Keep everything before the review section + only the last attempt
            before_review = content[:review_header]
            after_last_attempt = content[last_attempt_start:]
            content_opt = before_review + "== PRIOR REVIEW CONCLUSIONS ==\n\n" + after_last_attempt
            msgs_b[1]["content"] = content_opt
            print(f"  Original: {len(content)} chars, Optimized: {len(content_opt)} chars")
            print(f"  Removed {len(content) - len(content_opt)} chars of prior attempts")
        else:
            # Fallback: just find the first attempt and replace everything before last
            first_attempt_start = attempt_matches[0].start()
            before_attempts = content[:first_attempt_start]
            after_last = content[last_attempt_start:]
            content_opt = before_attempts + after_last
            msgs_b[1]["content"] = content_opt
            print(f"  Original: {len(content)} chars, Optimized: {len(content_opt)} chars")

        results_a, results_b = run_ab(
            "A-all-attempts", msgs_a, tools, "B-latest-only", msgs_b, tools
        )
        summarize(results_a, results_b, "A-all-attempts", "B-latest-only")
    else:
        print("  ERROR: Not enough attempt blocks found!")


# ============================================================
# TEST 4: Remove RECAP messages
# ============================================================
def test4(events):
    print("\n" + "=" * 70)
    print("TEST 4: Remove RECAP messages")
    print("=" * 70)

    # Use line 268 (32 msgs, 3 recaps, mid-SAM worker)
    # Actually let's use a longer one for more signal: line 506 (39 msgs, 4 recaps)
    ev = events[506]
    msgs, tools = parse_msgs_tools(ev)

    recap_indices = []
    for j, m in enumerate(msgs):
        c = m.get("content", "")
        if isinstance(c, str) and "[Recap:" in c:
            recap_indices.append(j)

    print(f"Source: line 506, {len(msgs)} msgs, RECAP messages at indices {recap_indices}")

    # Baseline A: original with RECAPs
    msgs_a = copy.deepcopy(msgs)

    # Optimized B: remove RECAP user messages
    # Need to be careful: RECAP is a user message, the assistant response after it
    # is paired with it. We should remove the RECAP user message and the assistant
    # response that follows it (since the assistant's response was conditioned on the RECAP).
    # Actually - let's just remove the RECAP user messages themselves.
    # But we need to be careful about the message flow (user/assistant/tool alternation).
    # The RECAP is a user message injected between tool result and assistant response.
    # Removing just the RECAP user message should be fine since the next message is assistant.

    msgs_b = []
    skip_next_assistant = False
    for j, m in enumerate(msgs):
        c = m.get("content", "")
        is_recap = isinstance(c, str) and "[Recap:" in c
        if is_recap:
            # Skip this RECAP user message and the assistant response after it
            skip_next_assistant = True
            continue
        if skip_next_assistant and m.get("role") == "assistant":
            skip_next_assistant = False
            continue
        skip_next_assistant = False
        msgs_b.append(m)

    print(f"  Original: {len(msgs_a)} messages, Optimized: {len(msgs_b)} messages")
    print(f"  Removed {len(msgs_a) - len(msgs_b)} messages")

    results_a, results_b = run_ab("A-with-recaps", msgs_a, tools, "B-no-recaps", msgs_b, tools)
    summarize(results_a, results_b, "A-with-recaps", "B-no-recaps")


def main():
    print("Loading cam log...")
    events = load_events()
    print(f"Loaded {len(events)} events from {CAM_FILE}")

    # Check gateway
    try:
        r = requests.get("http://localhost:11000/v1/models", timeout=10)
        r.raise_for_status()
        print(f"Gateway OK: {[m['id'] for m in r.json()['data'][:5]]}")
    except Exception as e:
        print(f"Gateway check failed: {e}")
        sys.exit(1)

    tests = {
        "1": test1,
        "2": test2,
        "3": test3,
        "4": test4,
    }

    if len(sys.argv) > 1:
        for t in sys.argv[1:]:
            if t in tests:
                tests[t](events)
            else:
                print(f"Unknown test: {t}")
    else:
        for t in sorted(tests):
            tests[t](events)

    print("\n" + "=" * 70)
    print("ALL TESTS COMPLETE")
    print("=" * 70)


if __name__ == "__main__":
    main()
