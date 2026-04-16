"""Example tool skill — echoes input with metadata."""
import os, time

def execute(args, task_dir):
    msg = args.get("message", "")
    if args.get("uppercase"):
        msg = msg.upper()
    return f"[echo] {msg} (from {os.path.basename(task_dir)} at {time.strftime('%H:%M:%S')})"
