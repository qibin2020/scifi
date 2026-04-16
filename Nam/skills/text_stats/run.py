"""Text statistics: count words, lines, chars in a file."""
import os

def execute(args, task_dir):
    path = args["path"]
    if not os.path.isabs(path):
        path = os.path.join(task_dir, path)
    with open(path) as f:
        text = f.read()
    lines = text.count('\n')
    words = len(text.split())
    chars = len(text)
    return f"lines={lines} words={words} chars={chars}"
