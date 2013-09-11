import sys
from mailpile.app import Main

# Load the standard plugins
from mailpile.plugins import *


def main():
    Main(sys.argv[1:])


if __name__ == "__main__":
    main()
