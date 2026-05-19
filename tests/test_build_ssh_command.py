import pytest
from ssh_ansible.ansible_ssh import build_ssh_command, parse_extra_ssh_options


class TestBuildSshCommand:

    def test_minimal_empty_vars(self):
        cmd, pw, target = build_ssh_command({}, "myhost")
        assert cmd == ["ssh", "myhost"]
        assert pw is None
        assert target == "myhost"

    def test_ansible_host(self):
        cmd, pw, target = build_ssh_command({"ansible_host": "192.168.1.10"}, "myhost")
        assert target == "192.168.1.10"
        assert cmd[-1] == "192.168.1.10"

    def test_ansible_ssh_host_takes_precedence(self):
        _, _, target = build_ssh_command(
            {"ansible_ssh_host": "10.0.0.1", "ansible_host": "10.0.0.2"}, "myhost"
        )
        assert target == "10.0.0.1"

    def test_ansible_user(self):
        _, _, target = build_ssh_command({"ansible_user": "bob"}, "myhost")
        assert target == "bob@myhost"

    def test_ansible_ssh_user_takes_precedence(self):
        _, _, target = build_ssh_command(
            {"ansible_ssh_user": "alice", "ansible_user": "bob"}, "myhost"
        )
        assert target == "alice@myhost"

    def test_port(self):
        cmd, _, _ = build_ssh_command({"ansible_port": 2222}, "myhost")
        idx = cmd.index("-p")
        assert cmd[idx + 1] == "2222"

    def test_private_key(self):
        cmd, _, _ = build_ssh_command(
            {"ansible_private_key_file": "/home/user/.ssh/id_rsa"}, "myhost"
        )
        idx = cmd.index("-i")
        assert cmd[idx + 1] == "/home/user/.ssh/id_rsa"

    def test_password_returned_not_in_cmd(self):
        cmd, pw, _ = build_ssh_command({"ansible_ssh_pass": "s3cr3t"}, "myhost")
        assert pw == "s3cr3t"
        assert "s3cr3t" not in cmd

    def test_ansible_password_fallback(self):
        _, pw, _ = build_ssh_command({"ansible_password": "fallback"}, "myhost")
        assert pw == "fallback"

    def test_ansible_ssh_pass_takes_precedence(self):
        _, pw, _ = build_ssh_command(
            {"ansible_ssh_pass": "primary", "ansible_password": "secondary"}, "myhost"
        )
        assert pw == "primary"

    def test_proxy_command_in_cmd(self):
        cmd, _, _ = build_ssh_command(
            {"ansible_ssh_common_args": '-o ProxyCommand="ssh -W %h:%p bastion"'},
            "myhost",
        )
        assert "-o" in cmd
        assert any("ProxyCommand" in arg for arg in cmd)

    def test_target_is_last_element(self):
        host_vars = {
            "ansible_host": "10.0.0.5",
            "ansible_user": "admin",
            "ansible_port": 2222,
        }
        cmd, _, target = build_ssh_command(host_vars, "server1")
        assert cmd[-1] == target == "admin@10.0.0.5"

    def test_full_combination_no_password_in_cmd(self):
        host_vars = {
            "ansible_host": "10.0.0.5",
            "ansible_user": "admin",
            "ansible_port": 2222,
            "ansible_private_key_file": "/key",
            "ansible_ssh_pass": "topsecret",
        }
        cmd, pw, _ = build_ssh_command(host_vars, "server1")
        assert cmd[0] == "ssh"
        assert pw == "topsecret"
        assert "topsecret" not in cmd


class TestParseExtraSshOptions:

    def test_empty_vars(self):
        assert parse_extra_ssh_options({}) == []

    def test_common_args_parsed(self):
        opts = parse_extra_ssh_options(
            {"ansible_ssh_common_args": "-o StrictHostKeyChecking=no"}
        )
        assert opts == ["-o", "StrictHostKeyChecking=no"]

    def test_extra_args_parsed(self):
        opts = parse_extra_ssh_options(
            {"ansible_ssh_extra_args": "-o ForwardAgent=yes"}
        )
        assert opts == ["-o", "ForwardAgent=yes"]

    def test_both_combined_in_order(self):
        opts = parse_extra_ssh_options({
            "ansible_ssh_common_args": "-o StrictHostKeyChecking=no",
            "ansible_ssh_extra_args": "-o ForwardAgent=yes",
        })
        assert "StrictHostKeyChecking=no" in opts
        assert "ForwardAgent=yes" in opts

    def test_proxy_jump(self):
        opts = parse_extra_ssh_options(
            {"ansible_ssh_common_args": "-J bastion.example.com"}
        )
        assert opts == ["-J", "bastion.example.com"]

    def test_invalid_shlex_exits(self):
        with pytest.raises(SystemExit):
            parse_extra_ssh_options({"ansible_ssh_common_args": "'-unclosed"})
