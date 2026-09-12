"""The conversational helper: facts in, one explained suggestion out.

Entry point is ``chordcat.helper.cli.analyse_capture``. It is deliberately not
re-exported here: ``python -m chordcat.helper.cli`` would then import the CLI
twice, once as a submodule and once as ``__main__``.
"""
