from emporio_agent import cli


def test_cli_importable():
    assert callable(cli.main)
