"""
Brainfuck interpreter.
"""


def run(code: str, input_data: str = "") -> str:
    tape = [0] * 30000
    ptr = 0
    ip = 0
    inp = iter(input_data)
    output = []

    # Pre-build bracket jump table for O(1) lookups
    jumps = {}
    stack = []
    for i, ch in enumerate(code):
        if ch == "[":
            stack.append(i)
        elif ch == "]":
            j = stack.pop()
            jumps[j] = i
            jumps[i] = j

    instructions = code
    length = len(instructions)

    while ip < length:
        cmd = instructions[ip]
        if cmd == ">":
            ptr = (ptr + 1) % 30000
        elif cmd == "<":
            ptr = (ptr - 1) % 30000
        elif cmd == "+":
            tape[ptr] = (tape[ptr] + 1) % 256
        elif cmd == "-":
            tape[ptr] = (tape[ptr] - 1) % 256
        elif cmd == ".":
            output.append(chr(tape[ptr]))
        elif cmd == ",":
            try:
                tape[ptr] = ord(next(inp))
            except StopIteration:
                tape[ptr] = 0
        elif cmd == "[":
            if tape[ptr] == 0:
                ip = jumps[ip]
        elif cmd == "]":
            if tape[ptr] != 0:
                ip = jumps[ip]
        ip += 1

    return "".join(output)
