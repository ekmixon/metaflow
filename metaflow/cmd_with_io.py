import subprocess
from .exception import ExternalCommandFailed

from metaflow.util import to_bytes

def cmd(cmdline, input, output):
    for path, data in input.items():
        with open(path, 'wb') as f:
            f.write(to_bytes(data))

    if subprocess.call(cmdline, shell=True):
        raise ExternalCommandFailed("Command '%s' returned a non-zero "
                                    "exit code." % cmdline)

    out = []
    for path in output:
        with open(path, 'rb') as f:
            out.append(f.read())

    return out[0] if len(out) == 1 else out
