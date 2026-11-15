"""Production-only entry: no self-check command-line interfaces."""
from ff14_app import main
if __name__=='__main__':raise SystemExit(main(release=True))
