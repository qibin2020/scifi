---
Rank: 0
BashTime: -1
NoMemory: on
Skills: common_env
CommonStorage: rw
---

# Cold Start — C++ Toolchain

## Context
Test that the common_env skill can set up a C++ compilation environment.

## Todo
1. Use the common_env skill to create a shared env with g++ (gxx_linux-64) and make
2. Write `hello.cpp` that prints "Hello from C++"
3. Compile and run it
4. Write the output to `result.txt`

## Expect
- `result.txt` exists and contains "Hello from C++"
- The environment is at /mnt/sci_envs/ (not local ./)
