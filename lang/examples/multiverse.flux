# ── Flux Parallel Universe Demo ────────────────────────────────────────────
#
# BRANCH opens a parallel universe. Each BRANCH block runs independently
# with its own copy of the current state. MERGE picks the winner.
#
#   MERGE MAX var   keep the branch where var is largest
#   MERGE MIN var   keep the branch where var is smallest
#   MERGE FIRST     keep the first branch that ran without error
#
# After MERGE, the winning branch's variables replace the current state.

PRINT "=== Parallel Universe: Portfolio Optimizer ==="
PRINT ""

# You have $1000. Three universes try different allocation strategies.
# The one with the highest portfolio value wins.

capital = 1000

BRANCH
  # Universe A: aggressive (80% tech, 20% bonds)
  tech_pct  = 80
  bond_pct  = 20
  tech_gain = 135   # +35%  (expressed as percentage of original, i.e. 135%)
  bond_gain = 105   # +5%
  portfolio = capital * tech_pct / 100 * tech_gain / 100
  portfolio = portfolio + capital * bond_pct / 100 * bond_gain / 100
  strategy  = 1

BRANCH
  # Universe B: balanced (50/50)
  tech_pct  = 50
  bond_pct  = 50
  tech_gain = 135
  bond_gain = 105
  portfolio = capital * tech_pct / 100 * tech_gain / 100
  portfolio = portfolio + capital * bond_pct / 100 * bond_gain / 100
  strategy  = 2

BRANCH
  # Universe C: conservative (10% tech, 90% bonds)
  tech_pct  = 10
  bond_pct  = 90
  tech_gain = 135
  bond_gain = 105
  portfolio = capital * tech_pct / 100 * tech_gain / 100
  portfolio = portfolio + capital * bond_pct / 100 * bond_gain / 100
  strategy  = 3

MERGE MAX portfolio

PRINT "Winning strategy (1=aggressive 2=balanced 3=conservative):"
PRINT strategy
PRINT "Final portfolio value:"
PRINT portfolio


# ── MERGE FIRST: Error tolerance ──────────────────────────────────────────

PRINT ""
PRINT "=== MERGE FIRST: Fault-Tolerant Branches ==="
PRINT ""

x = 10

BRANCH
  # This branch will crash (division by zero)
  zero = 0
  bad  = x / zero

BRANCH
  # This branch succeeds
  result = x * 7
  label  = 2

MERGE FIRST

PRINT "Surviving branch:"
PRINT label       # 2
PRINT "Result:"
PRINT result      # 70


# ── Nested time travel inside a universe ─────────────────────────────────

PRINT ""
PRINT "=== Multiverse + Time Travel ==="
PRINT ""

# Each universe rolls its own dice and keeps the result.
# The universe with the highest total wins.

BRANCH
  ROLL 1 20 r1
  ROLL 1 20 r2
  total = r1 + r2
  branch_id = 1

BRANCH
  ROLL 1 20 r1
  ROLL 1 20 r2
  total = r1 + r2
  branch_id = 2

BRANCH
  ROLL 1 20 r1
  ROLL 1 20 r2
  total = r1 + r2
  branch_id = 3

MERGE MAX total

PRINT "Winning universe:"
PRINT branch_id
PRINT "Winning total (2d20):"
PRINT total
