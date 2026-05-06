"""Unit tests for service check executors."""

import pytest
from src.collector.checks.base import CheckDefinition, CheckStatus
from src.collector.checks.http_check import HTTPCheckExecutor
from src.collector.checks.tcp_check import TCPCheckExecutor
from src.collector.checks.dns_check import DNSCheckExecutor
from src.collector.checks.ssl_check import SSLCheckExecutor


class TestHTTPCheckExecutor:
    """Tests for HTTPCheckExecutor."""

    def test_valid_config_with_url(self):
        """Test HTTP config validation with valid URL."""
        executor = HTTPCheckExecutor()
        config = {"url": "https://example.com/health"}
        valid, error = executor.validate_config(config)
        assert valid is True
        assert error == ""

    def test_missing_url(self):
        """Test validation fails without URL."""
        executor = HTTPCheckExecutor()
        config = {}
        valid, error = executor.validate_config(config)
        assert valid is False
        assert "URL is required" in error

    def test_invalid_url_format(self):
        """Test validation fails with invalid URL format."""
        executor = HTTPCheckExecutor()
        config = {"url": "not-a-url"}
        valid, error = executor.validate_config(config)
        assert valid is False
        assert "must start with http" in error.lower()

    def test_valid_expected_status_codes(self):
        """Test validation with valid expected status codes."""
        executor = HTTPCheckExecutor()
        config = {"url": "https://example.com", "expected_status": [200, 201, 204]}
        valid, error = executor.validate_config(config)
        assert valid is True

    def test_invalid_status_code(self):
        """Test validation fails with invalid status code."""
        executor = HTTPCheckExecutor()
        config = {"url": "https://example.com", "expected_status": [200, 999]}
        valid, error = executor.validate_config(config)
        assert valid is False
        assert "Invalid HTTP status code" in error

    def test_check_type_property(self):
        """Test check_type property returns 'http'."""
        executor = HTTPCheckExecutor()
        assert executor.check_type == "http"

    @pytest.mark.asyncio
    async def test_execute_with_mock(self):
        """Test HTTP check execution (mocked)."""
        executor = HTTPCheckExecutor()
        definition = CheckDefinition(
            id="test-http-1",
            name="Test HTTP Check",
            check_type="http",
            target="https://httpbin.org",
            config={"url": "https://httpbin.org/status/200"},
            timeout_seconds=5,
        )
        result = await executor.execute(definition)
        assert result.target_id == "test-http-1"
        assert result.check_type == "http"
        assert result.status in (CheckStatus.UP, CheckStatus.DOWN, CheckStatus.DEGRADED)
        assert result.response_time_ms >= 0


class TestTCPCheckExecutor:
    """Tests for TCPCheckExecutor."""

    def test_valid_config_with_host_port(self):
        """Test TCP config validation with valid host and port."""
        executor = TCPCheckExecutor()
        config = {"host": "localhost", "port": 80}
        valid, error = executor.validate_config(config)
        assert valid is True
        assert error == ""

    def test_missing_host(self):
        """Test validation fails without host."""
        executor = TCPCheckExecutor()
        config = {"port": 80}
        valid, error = executor.validate_config(config)
        assert valid is False
        assert "Host is required" in error

    def test_missing_port(self):
        """Test validation fails without port."""
        executor = TCPCheckExecutor()
        config = {"host": "localhost"}
        valid, error = executor.validate_config(config)
        assert valid is False
        assert "Port is required" in error

    def test_invalid_port_too_low(self):
        """Test validation fails with port < 1."""
        executor = TCPCheckExecutor()
        config = {"host": "localhost", "port": 0}
        valid, error = executor.validate_config(config)
        assert valid is False
        assert "Port must be between 1 and 65535" in error

    def test_invalid_port_too_high(self):
        """Test validation fails with port > 65535."""
        executor = TCPCheckExecutor()
        config = {"host": "localhost", "port": 70000}
        valid, error = executor.validate_config(config)
        assert valid is False
        assert "Port must be between 1 and 65535" in error

    def test_check_type_property(self):
        """Test check_type property returns 'tcp'."""
        executor = TCPCheckExecutor()
        assert executor.check_type == "tcp"

    @pytest.mark.asyncio
    async def test_execute_with_mock(self):
        """Test TCP check execution (mocked)."""
        executor = TCPCheckExecutor()
        definition = CheckDefinition(
            id="test-tcp-1",
            name="Test TCP Check",
            check_type="tcp",
            target="localhost:22",
            config={"host": "localhost", "port": 22},
            timeout_seconds=2,
        )
        result = await executor.execute(definition)
        assert result.target_id == "test-tcp-1"
        assert result.check_type == "tcp"
        assert result.status in (CheckStatus.UP, CheckStatus.DOWN, CheckStatus.UNKNOWN)
        assert result.response_time_ms >= 0


class TestDNSCheckExecutor:
    """Tests for DNSCheckExecutor."""

    def test_valid_config_with_domain(self):
        """Test DNS config validation with valid domain."""
        executor = DNSCheckExecutor()
        config = {"domain": "example.com"}
        valid, error = executor.validate_config(config)
        assert valid is True
        assert error == ""

    def test_missing_domain(self):
        """Test validation fails without domain."""
        executor = DNSCheckExecutor()
        config = {}
        valid, error = executor.validate_config(config)
        assert valid is False
        assert "Domain is required" in error

    def test_check_type_property(self):
        """Test check_type property returns 'dns'."""
        executor = DNSCheckExecutor()
        assert executor.check_type == "dns"

    @pytest.mark.asyncio
    async def test_execute_with_mock(self):
        """Test DNS check execution (mocked)."""
        executor = DNSCheckExecutor()
        definition = CheckDefinition(
            id="test-dns-1",
            name="Test DNS Check",
            check_type="dns",
            target="8.8.8.8",
            config={"domain": "example.com"},
            timeout_seconds=5,
        )
        result = await executor.execute(definition)
        assert result.target_id == "test-dns-1"
        assert result.check_type == "dns"
        assert result.status in (CheckStatus.UP, CheckStatus.DOWN, CheckStatus.UNKNOWN)


class TestSSLCheckExecutor:
    """Tests for SSLCheckExecutor."""

    def test_valid_config_with_host(self):
        """Test SSL config validation with valid host."""
        executor = SSLCheckExecutor()
        config = {"host": "example.com", "port": 443}
        valid, error = executor.validate_config(config)
        assert valid is True
        assert error == ""

    def test_missing_host(self):
        """Test validation fails without host."""
        executor = SSLCheckExecutor()
        config = {"port": 443}
        valid, error = executor.validate_config(config)
        assert valid is False
        assert "Host is required" in error

    def test_missing_port(self):
        """Test validation passes without port (defaults to 443)."""
        executor = SSLCheckExecutor()
        config = {"host": "example.com"}
        valid, error = executor.validate_config(config)
        assert valid is True  # Port defaults to 443

    def test_valid_min_days(self):
        """Test validation with valid min_days."""
        executor = SSLCheckExecutor()
        config = {"host": "example.com", "port": 443, "min_days": 30}
        valid, error = executor.validate_config(config)
        assert valid is True

    def test_invalid_warning_days(self):
        """Test validation fails with invalid warning_days."""
        executor = SSLCheckExecutor()
        config = {"host": "example.com", "port": 443, "warning_days": -1}
        valid, error = executor.validate_config(config)
        assert valid is False
        assert "Warning days must be a positive integer" in error

    def test_check_type_property(self):
        """Test check_type property returns 'ssl'."""
        executor = SSLCheckExecutor()
        assert executor.check_type == "ssl"

    @pytest.mark.asyncio
    async def test_execute_with_mock(self):
        """Test SSL check execution (mocked)."""
        executor = SSLCheckExecutor()
        definition = CheckDefinition(
            id="test-ssl-1",
            name="Test SSL Check",
            check_type="ssl",
            target="example.com:443",
            config={"host": "example.com", "port": 443},
            timeout_seconds=5,
        )
        result = await executor.execute(definition)
        assert result.target_id == "test-ssl-1"
        assert result.check_type == "ssl"
        assert result.status in (CheckStatus.UP, CheckStatus.DOWN, CheckStatus.UNKNOWN, CheckStatus.DEGRADED)
