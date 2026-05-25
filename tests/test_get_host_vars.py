import json
import os
import shutil
import subprocess
import pytest
from ssh_ansible.ansible_ssh import get_host_vars

pytestmark = pytest.mark.skipif(
    shutil.which("ansible-inventory") is None,
    reason="ansible-inventory not available",
)

REPO_ROOT = os.path.dirname(os.path.dirname(__file__))
INV_YAML = os.path.join(REPO_ROOT, "tests", "fixtures", "inventory")
INV_INI = os.path.join(REPO_ROOT, "tests", "fixtures", "hosts.ini")
INV_PROXY = os.path.join(REPO_ROOT, "tests", "fixtures", "hosts_proxy.yaml")
VAULT_PW_FILE = os.path.join(REPO_ROOT, "tests", "fixtures", "vault_password")


class TestGetHostVars:

    def test_returns_dict(self):
        result = get_host_vars(INV_YAML, "server1")
        assert isinstance(result, dict)

    def test_group_vars_resolved(self):
        # server1 has no host-specific vars but inherits from the group
        result = get_host_vars(INV_YAML, "server1")
        assert result.get("ansible_user") == "user1"
        assert result.get("ansible_port") == 2222

    def test_host_var_overrides_group_var(self):
        # server5 sets ansible_user=user2 overriding the group default user1
        result = get_host_vars(INV_YAML, "server5")
        assert result.get("ansible_user") == "user2"

    def test_unknown_host_exits(self):
        with pytest.raises(SystemExit):
            get_host_vars(INV_YAML, "nonexistent-host-xyz")

    def test_ini_inventory(self):
        result = get_host_vars(INV_INI, "server.hosts.ini")
        assert isinstance(result, dict)

    def test_proxy_inventory_host_vars(self):
        result = get_host_vars(INV_PROXY, "gold_vm")
        assert result.get("ansible_ssh_host") == "192.168.123.2"
        assert result.get("ansible_ssh_user") == "ansible"
        assert "ProxyCommand" in result.get("ansible_ssh_common_args", "")

    def test_vault_encrypted_password_without_key_is_dict(self):
        # Without a vault password, encrypted vars come back as {"__ansible_vault": ...} dicts
        result = get_host_vars(INV_YAML, "server_vault")
        raw = result.get("ansible_password")
        assert isinstance(raw, dict) and "__ansible_vault" in raw

    def test_vault_encrypted_password_decrypted(self):
        result = get_host_vars(INV_YAML, "server_vault", vault_password_file=VAULT_PW_FILE)
        assert result.get("ansible_password") == "vault_test_pass"
        assert result.get("ansible_user") == "vaultuser"
        assert result.get("ansible_host") == "10.0.0.99"


def _pick_host_from_inventory(inventory_path):
    """Return the first host found in an arbitrary inventory via ansible-inventory."""
    result = subprocess.run(
        ["ansible-inventory", "-i", inventory_path, "--list"],
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    data = json.loads(result.stdout)
    hostvars = data.get("_meta", {}).get("hostvars", {})
    if hostvars:
        return next(iter(hostvars))
    # Fall back to scanning group hosts lists
    for value in data.values():
        if isinstance(value, dict):
            hosts = value.get("hosts", [])
            if isinstance(hosts, list) and hosts:
                return hosts[0]
            if isinstance(hosts, dict) and hosts:
                return next(iter(hosts))
    return None


@pytest.mark.skipif(
    shutil.which("ansible-inventory") is None,
    reason="ansible-inventory not available",
)
class TestGetHostVarsExternal:
    """Integration tests that run against a user-supplied inventory.

    Pass --test-inventory=<path> on the pytest command line to enable these tests.
    They only verify structural/behavioural correctness without assuming specific
    variable values, so they work with any inventory.
    """

    def test_returns_dict_for_discovered_host(self, external_inventory, vault_password_file):
        host = _pick_host_from_inventory(external_inventory)
        assert host is not None, "Could not discover any host in the supplied inventory"
        result = get_host_vars(external_inventory, host, vault_password_file=vault_password_file)
        assert isinstance(result, dict)

    def test_all_values_are_scalars_or_none(self, external_inventory, vault_password_file):
        host = _pick_host_from_inventory(external_inventory)
        assert host is not None
        result = get_host_vars(external_inventory, host, vault_password_file=vault_password_file)
        for key, val in result.items():
            assert isinstance(key, str)
            # Vault-encrypted values appear as {"__ansible_vault": ...} dicts when no
            # vault password is supplied; that is valid and expected.
            assert (
                val is None
                or isinstance(val, (str, int, float, bool))
                or (isinstance(val, dict) and "__ansible_vault" in val)
            )

    def test_unknown_host_exits(self, external_inventory, vault_password_file):
        with pytest.raises(SystemExit):
            get_host_vars(external_inventory, "nonexistent-host-xyz-12345", vault_password_file=vault_password_file)
