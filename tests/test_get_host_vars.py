import os
import shutil
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
