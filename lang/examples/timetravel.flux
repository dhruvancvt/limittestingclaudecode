# ── Flux Time Travel Demo ──────────────────────────────────────────────────
#
# Two time-travel mechanics:
#
#   ANCHOR name / REWIND TO name
#     Save a named snapshot of all variables. Restore it later — no matter
#     how much state changed in between.
#
#   REWIND n
#     Undo the last n statements (restoring state to what it was n steps
#     ago) AND jump the program counter back n steps. Fires exactly once;
#     re-encountering it on the replay skips it.
#     Because ROLL generates a new number every time it executes, rewinding
#     past a ROLL gives you a genuinely different result.

# ── Part 1: ANCHOR / REWIND TO (named save-state) ─────────────────────────

PRINT "=== Part 1: ANCHOR / REWIND TO ==="

hp   = 100
gold = 50
PRINT "Starting:"
PRINT "  hp   ="
PRINT hp
PRINT "  gold ="
PRINT gold

ANCHOR before_dungeon

# Run the dungeon — take damage, collect loot
hp   = hp - 45
gold = gold + 200
hp   = hp - 30

PRINT "After dungeon:"
PRINT "  hp   ="
PRINT hp        # 25
PRINT "  gold ="
PRINT gold      # 250

# Load the save — instantly undo the whole dungeon run
REWIND TO before_dungeon

PRINT "Loaded save (dungeon undone):"
PRINT "  hp   ="
PRINT hp        # 100
PRINT "  gold ="
PRINT gold      # 50

# Take a different, safer path
gold = gold + 30
PRINT "After safe path:"
PRINT "  gold ="
PRINT gold      # 80


# ── Part 2: REWIND n (undo + jump, one-shot) ──────────────────────────────

PRINT ""
PRINT "=== Part 2: REWIND n ==="
PRINT ""
PRINT "Rolling 3d6 for stats..."

# Roll three dice and sum them
ROLL 1 6 d1
ROLL 1 6 d2
ROLL 1 6 d3
total = d1 + d2 + d3
PRINT "First roll total:"
PRINT total

# REWIND 6: undo 6 steps → state goes back to before d1 was rolled.
# Execution jumps back to the first ROLL, which generates new random values.
# On the replay the REWIND instruction is marked consumed and skipped.
REWIND 6

PRINT "After rewind — new roll total:"
PRINT total
