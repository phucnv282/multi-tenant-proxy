import sys
import getopt
from routes import run_app


def init_service(argv = None):
    port = 8080
    opts, args = getopt.getopt(argv, "hp:", ["port="])
    if opts:
        for opt, arg in opts:
            if opt in ("-p", "--port"):
                port = arg
    run_app(port)


if __name__ == "__main__":
    init_service(sys.argv[1:])
