---
Rank: 1
BashTime: -1
NoMemory: on
Skills: common_env
---

# Build and run a C++ hello world (shared env)

## Context

Write a C++ program that prints "Hello from C++" and a Python script that imports numpy and prints the numpy version. Both must compile/run successfully.

Use the `common_env` skill to find or set up a shared environment with a C++ compiler and numpy.

## Todo

1. Set up a working environment with g++ and numpy via the common_env skill.
2. Write `hello.cpp` that prints "Hello from C++".
3. Compile and run it.
4. Write `check_numpy.py` that does `import numpy; print(numpy.__version__)`.
5. Run it.

## Expect

- `hello.cpp` exists and compiles
- Running the compiled binary prints "Hello from C++"
- `check_numpy.py` runs and prints a numpy version string
- `output.txt` contains both outputs
