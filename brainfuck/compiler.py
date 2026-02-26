"""
Python to Brainfuck compiler.
Compiles a tiny subset of Python into Brainfuck assembly.
"""


class BFCompiler:
    """Compiles simplified Python-like expressions to Brainfuck."""

    def __init__(self):
        self.output = []       # BF instruction list
        self.variables = {}    # name -> cell index
        self.next_cell = 0     # next free cell

    # ------------------------------------------------------------------
    # Low-level cell helpers
    # ------------------------------------------------------------------

    def _alloc(self, name: str) -> int:
        """Allocate a new cell for a variable and return its index."""
        if name not in self.variables:
            self.variables[name] = self.next_cell
            self.next_cell += 1
        return self.variables[name]

    def _emit(self, code: str):
        self.output.append(code)

    def _move_to(self, cell: int, current: list):
        """Emit pointer moves from current[0] to cell, update current."""
        diff = cell - current[0]
        if diff > 0:
            self._emit(">" * diff)
        elif diff < 0:
            self._emit("<" * (-diff))
        current[0] = cell

    def _zero_cell(self, cell: int, current: list):
        """Zero out a cell:  [-]"""
        self._move_to(cell, current)
        self._emit("[-]")

    def _set_cell(self, cell: int, value: int, current: list):
        """Set a cell to an integer constant (0-255)."""
        self._zero_cell(cell, current)
        if value > 0:
            self._emit("+" * value)

    # ------------------------------------------------------------------
    # Public compilation helpers
    # ------------------------------------------------------------------

    def assign(self, name: str, value: int):
        """Assign a constant integer to a variable."""
        cell = self._alloc(name)
        cur = [0]
        self._move_to(cell, cur)
        self._set_cell(cell, value % 256, cur)
        # return pointer to cell 0
        self._move_to(0, cur)

    def add(self, dest: str, src: str):
        """dest += src  (destructively reads src into dest)."""
        dc = self._alloc(dest)
        sc = self._alloc(src)
        cur = [0]
        # Move to src, loop moving each unit to dest
        self._move_to(sc, cur)
        self._emit("[")
        self._emit("-")
        self._move_to(dc, cur)
        self._emit("+")
        self._move_to(sc, cur)
        self._emit("]")
        self._move_to(0, cur)

    def print_var(self, name: str):
        """Output (print) a variable's cell value as a character."""
        cell = self._alloc(name)
        cur = [0]
        self._move_to(cell, cur)
        self._emit(".")
        self._move_to(0, cur)

    def print_const(self, value: int):
        """Print a constant character value."""
        tmp = "__tmp__"
        self.assign(tmp, value)
        self.print_var(tmp)

    def print_string(self, text: str):
        """Print a string literal character by character."""
        prev = 0
        tmp = "__tmp__"
        tc = self._alloc(tmp)
        cur = [0]
        self._move_to(tc, cur)
        for ch in text:
            v = ord(ch)
            diff = v - prev
            if diff > 0:
                self._emit("+" * diff)
            elif diff < 0:
                self._emit("-" * (-diff))
            self._emit(".")
            prev = v
        # zero out tmp when done
        self._zero_cell(tc, cur)
        self._move_to(0, cur)

    # ------------------------------------------------------------------
    # Finalise
    # ------------------------------------------------------------------

    def compile(self) -> str:
        return "".join(self.output)
