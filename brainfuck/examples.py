"""
Example programs compiled from Python-style source to Brainfuck.
Run this file to see them in action.
"""

from compiler import BFCompiler
from interpreter import run


def example_hello_world():
    print("=== Hello, World! ===")
    c = BFCompiler()
    c.print_string("Hello, World!\n")
    bf = c.compile()
    print("BF code:", bf)
    print("Output:", run(bf))


def example_addition():
    print("=== Addition: a=3, b=4, print a+b as char ===")
    c = BFCompiler()
    c.assign("a", 3)
    c.assign("b", 4)
    c.add("a", "b")       # a = a + b = 7
    # 7 isn't printable — let's do something visible: 'A'(65) + 3 = 68 = 'D'
    c2 = BFCompiler()
    c2.assign("a", 65)    # 'A'
    c2.assign("b", 3)
    c2.add("a", "b")      # a = 68 = 'D'
    c2.print_var("a")
    c2.print_string("\n")
    bf = c2.compile()
    print("BF code:", bf)
    print("Output:", run(bf))


def example_greeting():
    print("=== Custom greeting ===")
    c = BFCompiler()
    c.print_string("BF says: Hi!\n")
    bf = c.compile()
    print("BF code:", bf)
    print("Output:", run(bf))


if __name__ == "__main__":
    example_hello_world()
    print()
    example_addition()
    print()
    example_greeting()
