import pytest


def pytest_addoption(parser):
    parser.addoption(
        "--test-inventory",
        action="store",
        default=None,
        metavar="PATH",
        help="Path to an external Ansible inventory file for integration tests",
    )


@pytest.fixture
def external_inventory(request):
    """Fixture that resolves to the path passed via --test-inventory.

    Tests using this fixture are automatically skipped when the option is absent.
    """
    inv = request.config.getoption("--test-inventory")
    if inv is None:
        pytest.skip("No external inventory provided — pass --test-inventory=<path>")
    return inv
