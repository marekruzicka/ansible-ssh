import os
import pytest
from ssh_ansible.ansible_ssh import find_ansible_cfg, get_default_inventory_from_cfg

REPO_ROOT = os.path.dirname(os.path.dirname(__file__))
TEST_FILES = os.path.join(REPO_ROOT, "test_files")


class TestGetDefaultInventoryFromCfg:

    def test_reads_inventory_key(self):
        inv = get_default_inventory_from_cfg(os.path.join(TEST_FILES, "ansible.cfg"))
        assert inv == "inventory"

    def test_missing_file_returns_none(self):
        assert get_default_inventory_from_cfg("/nonexistent/path/ansible.cfg") is None

    def test_cfg_without_inventory_returns_none(self, tmp_path):
        cfg = tmp_path / "ansible.cfg"
        cfg.write_text("[defaults]\n# no inventory setting\n")
        assert get_default_inventory_from_cfg(str(cfg)) is None


class TestFindAnsibleCfg:

    def test_finds_via_env_var(self, monkeypatch, tmp_path):
        cfg = tmp_path / "custom.cfg"
        cfg.write_text("[defaults]\n")
        monkeypatch.setenv("ANSIBLE_CONFIG", str(cfg))
        assert find_ansible_cfg() == str(cfg)

    def test_env_var_takes_precedence_over_cwd(self, monkeypatch, tmp_path):
        env_cfg = tmp_path / "env.cfg"
        env_cfg.write_text("[defaults]\n")
        cwd_cfg = tmp_path / "ansible.cfg"
        cwd_cfg.write_text("[defaults]\n")
        monkeypatch.chdir(tmp_path)
        monkeypatch.setenv("ANSIBLE_CONFIG", str(env_cfg))
        assert find_ansible_cfg() == str(env_cfg)

    def test_finds_in_cwd(self, monkeypatch, tmp_path):
        cfg = tmp_path / "ansible.cfg"
        cfg.write_text("[defaults]\n")
        monkeypatch.chdir(tmp_path)
        monkeypatch.delenv("ANSIBLE_CONFIG", raising=False)
        assert find_ansible_cfg() == str(cfg)
