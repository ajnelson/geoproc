
import sys
import argparse

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Unit test")
    parser.add_argument("-r","--regress", action="store_true", dest="regress", help="Run regression tests and exit")
    parser.add_argument("foo", help="Give this a value")
    args0 = parser.parse_known_args()[0]

    if args0.regress:
        sys.stdout.write(args0.foo)
        sys.exit(0)

    parser.add_argument("bar", help="Give this a value")
    args1 = parser.parse_args()
    sys.stdout.write(args1.foo + args1.bar)
