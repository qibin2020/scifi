# Skill Template

Two skill types are supported:

## Type 1: Tool Skill (skill.yaml + run.py)
Adds a callable tool to the agent's toolkit.

```
my_skill/
├── skill.yaml    # manifest: name, description, tool schema
├── run.py        # execute(args, task_dir) → string
└── README.md     # human docs (optional)
```

### skill.yaml format:
```yaml
name: my_skill
description: One-line description for catalog and prescan.
tool:
  name: my_skill
  description: What the tool does (shown to agent).
  parameters:
    param1:
      type: string
      required: true
      description: What this param is
    param2:
      type: integer
      description: Optional param
```

### run.py format:
```python
"""Docstring describing the skill."""
import os

def execute(args, task_dir):
    """Called when agent uses this tool.
    args: dict from tool call (matches parameters in skill.yaml)
    task_dir: working directory of the current task
    Returns: string result shown to agent
    """
    param1 = args["param1"]
    # ... do work ...
    return "result string"
```

## Type 2: Context Skill (SKILL.md)
Injects instructions/knowledge into the agent's context. No callable tool.
Agent uses existing tools (bash, read_file, etc.) guided by the instructions.

```
my_knowledge_skill/
├── SKILL.md      # frontmatter (name, description) + instructions
├── templates/    # reference templates (optional)
└── README.md     # human docs (optional)
```

### SKILL.md format:
```markdown
---
name: my_knowledge_skill
description: One-line description for catalog and prescan.
---

Full instructions the agent receives in context.
Include: workflow steps, rules, templates, examples.
The agent follows these using bash/read_file/write_file tools.
```

## Usage in Tasks
Reference skills in task .md metadata:
```markdown
Rank: 2
Skills: my_skill, my_knowledge_skill
```

Prescan reads the catalog and selects which skills the task needs.
Tool skills add tools. Context skills add instructions.
