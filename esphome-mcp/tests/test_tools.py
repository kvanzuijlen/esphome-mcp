import os
import tempfile
import pytest

from server import tools

def test_safe_path_valid():
    with tempfile.TemporaryDirectory() as tmpdir:
        # Valid path
        resolved = tools.safe_path(tmpdir, "device.yaml")
        assert resolved == os.path.realpath(os.path.join(tmpdir, "device.yaml"))

def test_safe_path_traversal():
    with tempfile.TemporaryDirectory() as tmpdir:
        # Invalid path traversal
        with pytest.raises(PermissionError):
            tools.safe_path(tmpdir, "../outside.yaml")

        # Complex path traversal
        with pytest.raises(PermissionError):
            tools.safe_path(tmpdir, "subdir/../../outside.yaml")

def test_parse_device_info_custom_tags():
    content = """
esphome:
  name: test-device
  friendly_name: Test Device Friendly

wifi:
  ssid: !secret wifi_ssid
  password: !secret wifi_password

sensor:
  - platform: template
    name: "Custom Sensor"
    lambda: !lambda |-
      return 42.0;

  - platform: other
    custom_tag: !custom_tag [1, 2, 3]
"""
    with tempfile.NamedTemporaryFile(suffix=".yaml", delete=False, mode="w", encoding="utf-8") as f:
        f.write(content)
        temp_path = f.name

    try:
        info = tools._parse_device_info(temp_path)
        assert info["name"] == "test-device"
        assert info["friendly_name"] == "Test Device Friendly"
        assert info["file"] == os.path.basename(temp_path)
        assert "error" not in info
    finally:
        os.unlink(temp_path)

def test_parse_device_info_empty_or_invalid():
    with tempfile.NamedTemporaryFile(suffix=".yaml", delete=False, mode="w", encoding="utf-8") as f:
        f.write("invalid: yaml: :")
        temp_path = f.name

    try:
        info = tools._parse_device_info(temp_path)
        assert info["name"] == "error"
        assert "error" in info
    finally:
        os.unlink(temp_path)

import asyncio


def test_run_async_success(monkeypatch, tmp_path):
    monkeypatch.setattr(tools, "ESPHOME_DIR", str(tmp_path))
    res = asyncio.run(tools._run_async(["echo", "hello world"]))
    assert res == "hello world"


def test_run_async_timeout(monkeypatch, tmp_path):
    monkeypatch.setattr(tools, "ESPHOME_DIR", str(tmp_path))
    res = asyncio.run(tools._run_async(["sleep", "10"], timeout=1))
    assert "Command timed out after 1s" in res


def test_run_async_timeout_capture(monkeypatch, tmp_path):
    monkeypatch.setattr(tools, "ESPHOME_DIR", str(tmp_path))
    cmd = ["python3", "-c", "import time, sys; print('hello'); sys.stdout.flush(); time.sleep(5); print('world')"]
    res = asyncio.run(tools._run_async(cmd, timeout=1, capture_on_timeout=True))
    assert res == "hello"



def test_logs_streaming(monkeypatch, tmp_path):
    monkeypatch.setattr(tools, "ESPHOME_DIR", str(tmp_path))
    
    yaml_file = tmp_path / "testdevice.yaml"
    yaml_file.write_text("esphome:\n  name: testdevice\n", encoding="utf-8")
    
    mock_esphome = tmp_path / "mock_esphome"
    mock_esphome.write_text("""#!/bin/sh
if [ "$1" = "logs" ]; then
    echo "LOG1"
    echo "LOG2"
    sleep 10
fi
""", encoding="utf-8")
    mock_esphome.chmod(0o755)
    
    monkeypatch.setattr(tools, "ESPHOME_BIN", str(mock_esphome))
    
    res = asyncio.run(tools.logs("testdevice", num_lines=1, duration=1))
    assert res == "LOG2"


def test_list_devices(monkeypatch, tmp_path):
    monkeypatch.setattr(tools, "ESPHOME_DIR", str(tmp_path))
    
    d1 = tmp_path / "device1.yaml"
    d1.write_text("esphome:\n  name: dev1\n  friendly_name: Device One\n", encoding="utf-8")
    
    archive_dir = tmp_path / "archive"
    archive_dir.mkdir()
    d2 = archive_dir / "device2.yaml"
    d2.write_text("esphome:\n  name: dev2\n  friendly_name: Device Two\n", encoding="utf-8")
    
    d3 = tmp_path / "secrets.yaml"
    d3.write_text("secrets: secret\n", encoding="utf-8")
    
    res = tools.list_devices()
    assert "dev1" in res
    assert "Device One" in res
    assert "dev2" in res
    assert "Device Two" in res
    assert "[archived]" in res
    assert "secrets" not in res


def test_push_pull_files(monkeypatch, tmp_path):
    monkeypatch.setattr(tools, "ESPHOME_DIR", str(tmp_path))
    
    files = {
        "device1.yaml": "esphome:\n  name: dev1\n",
        "archive/device2.yaml": "esphome:\n  name: dev2\n",
        "secrets.yaml": "some secrets\n",
        "test.txt": "not yaml\n"
    }
    push_res = tools.push_files(files)
    assert "device1.yaml: OK" in push_res
    assert "archive/device2.yaml: OK" in push_res
    assert "secrets.yaml: REJECTED" in push_res
    assert "test.txt: REJECTED" in push_res
    
    assert (tmp_path / "device1.yaml").exists()
    assert (tmp_path / "archive" / "device2.yaml").exists()
    assert not (tmp_path / "secrets.yaml").exists()
    
    pull_res = tools.pull_files(["device1.yaml", "archive/device2.yaml"])
    assert "device1.yaml" in pull_res
    assert "archive/device2.yaml" in pull_res
    assert "dev1" in pull_res["device1.yaml"]
    assert "dev2" in pull_res["archive/device2.yaml"]


def test_push_pull_fonts(monkeypatch, tmp_path):
    monkeypatch.setattr(tools, "ESPHOME_DIR", str(tmp_path))
    
    import base64
    font_data = b"mock font binary data"
    b64_font = base64.b64encode(font_data).decode("ascii")
    
    push_res = tools.push_fonts({"testfont.ttf": b64_font})
    assert "testfont.ttf: OK" in push_res
    assert (tmp_path / "fonts" / "testfont.ttf").exists()
    assert (tmp_path / "fonts" / "testfont.ttf").read_bytes() == font_data
    
    pull_res = tools.pull_fonts(["testfont.ttf"])
    assert "testfont.ttf" in pull_res
    assert pull_res["testfont.ttf"] == b64_font


def test_compile_uses_custom_timeout(monkeypatch, tmp_path):
    monkeypatch.setattr(tools, "ESPHOME_DIR", str(tmp_path))
    monkeypatch.setattr(tools, "COMPILE_TIMEOUT", 42)
    
    yaml_file = tmp_path / "mydevice.yaml"
    yaml_file.write_text("esphome:\n  name: mydevice\n", encoding="utf-8")
    
    timeout_called = None
    async def mock_run_async(cmd, timeout, cwd=None, capture_on_timeout=False):
        nonlocal timeout_called
        timeout_called = timeout
        return "success"
        
    monkeypatch.setattr(tools, "_run_async", mock_run_async)
    
    asyncio.run(tools.compile_device("mydevice"))
    assert timeout_called == 42


def test_flash_uses_custom_timeout(monkeypatch, tmp_path):
    monkeypatch.setattr(tools, "ESPHOME_DIR", str(tmp_path))
    monkeypatch.setattr(tools, "FLASH_TIMEOUT", 99)
    
    yaml_file = tmp_path / "mydevice.yaml"
    yaml_file.write_text("esphome:\n  name: mydevice\n", encoding="utf-8")
    
    timeout_called = None
    async def mock_run_async(cmd, timeout, cwd=None, capture_on_timeout=False):
        nonlocal timeout_called
        timeout_called = timeout
        return "success"
        
    monkeypatch.setattr(tools, "_run_async", mock_run_async)
    
    asyncio.run(tools.flash("mydevice"))
    assert timeout_called == 99


def test_validate_uses_custom_timeout(monkeypatch, tmp_path):
    monkeypatch.setattr(tools, "ESPHOME_DIR", str(tmp_path))
    monkeypatch.setattr(tools, "VALIDATE_TIMEOUT", 7)
    
    yaml_file = tmp_path / "mydevice.yaml"
    yaml_file.write_text("esphome:\n  name: mydevice\n", encoding="utf-8")
    
    timeout_called = None
    async def mock_run_async(cmd, timeout, cwd=None, capture_on_timeout=False):
        nonlocal timeout_called
        timeout_called = timeout
        return "success"
        
    monkeypatch.setattr(tools, "_run_async", mock_run_async)
    
    asyncio.run(tools.validate("mydevice"))
    assert timeout_called == 7


def test_push_file_chunk(monkeypatch, tmp_path):
    monkeypatch.setattr(tools, "ESPHOME_DIR", str(tmp_path))
    
    # Overwrite/Create first chunk
    res = tools.push_file_chunk("test_chunk.yaml", "line1\n", append=False)
    assert "Success" in res
    assert (tmp_path / "test_chunk.yaml").read_text() == "line1\n"
    
    # Append second chunk
    res2 = tools.push_file_chunk("test_chunk.yaml", "line2\n", append=True)
    assert "Success" in res2
    assert (tmp_path / "test_chunk.yaml").read_text() == "line1\nline2\n"

    # Reject forbidden file
    res3 = tools.push_file_chunk("secrets.yaml", "secret content\n", append=False)
    assert "REJECTED" in res3

    # Reject non-yaml file
    res4 = tools.push_file_chunk("test.txt", "txt content\n", append=False)
    assert "REJECTED" in res4

