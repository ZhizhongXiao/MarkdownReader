"""The application version, as a runtime fact.

`pyproject.toml` states the release version, but it is not part of the packed payload
(`packaging/MarkdownReader.spec` ships the reader, not the build metadata) and this
repository declares itself not installable as a package, so `importlib.metadata` cannot
answer either. The About panel therefore reads this constant, and
`tests/test_version_contract.py` keeps the constant equal to the declared version --
without that bond the two drift and About starts misreporting which build is running.
"""

__version__ = "1.0.0rc1"
