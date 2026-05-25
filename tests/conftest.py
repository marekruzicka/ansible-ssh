import pytest


def pytest_addoption(parser):
    parser.addoption(
        "--test-inventory",
        action="store",
        default=None,
        metavar="PATH",
        help="Path to an external Ansible inventory file for integration tests",
    )
    parser.addoption(
        "--test-vault-password-file",
        action="store",
        default=None,
        metavar="FILE",
        help="Vault password file used when --test-inventory contains encrypted variables",
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


@pytest.fixture
def vault_password_file(request):
    """Optional vault password file passed via --test-vault-password-file.

    Returns None when the option is not supplied; tests still run but vault
    variables in the external inventory will remain as encrypted dicts.
    """
    return request.config.getoption("--test-vault-password-file")
