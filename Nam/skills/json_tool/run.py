"""JSON utilities: validate, pretty-print, query JSON files."""
import os, json

def execute(args, task_dir):
    path = args["path"]
    if not os.path.isabs(path):
        path = os.path.join(task_dir, path)
    with open(path) as f:
        data = json.load(f)
    query = args.get("query")
    if query:
        for key in query.split('.'):
            data = data[key]
    return json.dumps(data, indent=2) if isinstance(data, (dict, list)) else str(data)
