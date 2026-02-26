# ── Flux Calculator ────────────────────────────────────────────────────────
# Demonstrates: variables, INPUT, arithmetic, IF/ELSE

PRINT "=== Flux Calculator ==="
PRINT "Enter a:"
INPUT a
PRINT "Enter b:"
INPUT b

PRINT "a + b ="
PRINT a + b

PRINT "a - b ="
PRINT a - b

PRINT "a * b ="
PRINT a * b

IF b != 0 THEN
  PRINT "a / b ="
  PRINT a / b
  PRINT "a % b ="
  PRINT a % b
ELSE
  PRINT "b is zero — division skipped"
END

# Show the larger value
IF a >= b THEN
  PRINT "Larger value: a ="
  PRINT a
ELSE
  PRINT "Larger value: b ="
  PRINT b
END
