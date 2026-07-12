"""Compatibility loader for a locally corrupted Python 3.10 base64 module.

The host's standard-library file has an accidental shell fragment before its
first Python statement.  Load the original implementation unchanged after
that fragment so application imports keep the normal stdlib API.
"""

import os


_stdlib_base64 = os.path.join(os.path.dirname(os.__file__), 'base64.py')
with open(_stdlib_base64, encoding='utf-8') as _source_file:
    _source = _source_file.read()

if _source.startswith('base64 -w0 '):
    _source = _source.split('\n', 1)[1]

exec(compile(_source, _stdlib_base64, 'exec'), globals())
