"""Tests for payment service functions."""

from __future__ import annotations

from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


class TestPaymentServiceFunctions:
    """Test payment service helper functions."""

    def test_generate_order_no(self):
        """Test order number generation."""
        from app.services.payment import generate_order_no

        order_no = generate_order_no()
        assert order_no.startswith("MG")
        assert len(order_no) > 10

    def test_sign_epay_params(self):
        """Test EPay parameter signing."""
        from app.services.payment import _sign_epay_params

        params = {
            "pid": "1001",
            "type": "alipay",
            "out_trade_no": "ORD123",
            "notify_url": "https://example.com/notify",
            "return_url": "https://example.com/return",
            "name": "Test Order",
            "money": "100.00",
        }
        key = "secret_key"

        sign = _sign_epay_params(params, key)

        assert sign is not None
        assert len(sign) == 32  # MD5 hash length

    def test_sign_epay_params_sorted(self):
        """Test EPay parameter signing sorts params."""
        from app.services.payment import _sign_epay_params

        # Params in non-alphabetical order
        params = {
            "z_last": "value",
            "a_first": "value",
            "m_middle": "value",
        }
        key = "secret_key"

        sign = _sign_epay_params(params, key)
        assert sign is not None

    def test_build_epay_url(self):
        """Test building EPay payment URL."""
        from app.services.payment import _build_epay_url

        url = _build_epay_url(
            gateway_url="https://pay.example.com",
            pid="1001",
            key="secret_key",
            order_no="ORD123",
            amount=Decimal("100.00"),
            notify_url="https://example.com/notify",
            return_url="https://example.com/return",
            payment_type="alipay",
        )

        assert "https://pay.example.com/submit.php" in url
        assert "pid=1001" in url
        assert "out_trade_no=ORD123" in url
        assert "sign=" in url
        assert "sign_type=MD5" in url

    @pytest.mark.asyncio
    async def test_get_active_epay_config_found(self):
        """Test getting active EPay config when exists."""
        from app.services.payment import get_active_epay_config

        mock_db = AsyncMock()

        config_item = SimpleNamespace(
            id="config-1",
            type="epay",
            config={
                "url": "https://pay.example.com",
                "pid": "1001",
                "key": "secret_key",
                "payment_type": "alipay",
                "notify_url": "https://example.com/notify",
                "return_url": "https://example.com/return",
            },
        )

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = config_item
        mock_db.execute.return_value = mock_result

        result = await get_active_epay_config(mock_db)

        assert result is not None
        assert result["url"] == "https://pay.example.com"
        assert result["pid"] == "1001"

    @pytest.mark.asyncio
    async def test_get_active_epay_config_not_found(self):
        """Test getting active EPay config when not exists."""
        from app.services.payment import get_active_epay_config

        mock_db = AsyncMock()

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute.return_value = mock_result

        result = await get_active_epay_config(mock_db)

        assert result is None

    @pytest.mark.asyncio
    async def test_get_active_epay_config_missing_fields(self):
        """Test getting EPay config with missing required fields."""
        from app.services.payment import get_active_epay_config

        mock_db = AsyncMock()

        config_item = SimpleNamespace(
            id="config-1",
            type="epay",
            config={
                "url": "",  # Missing URL
                "pid": "1001",
            },
        )

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = config_item
        mock_db.execute.return_value = mock_result

        result = await get_active_epay_config(mock_db)

        assert result is None

    @pytest.mark.asyncio
    async def test_create_payment_order(self):
        """Test creating payment order."""
        from app.services.payment import create_payment_order

        mock_db = AsyncMock()

        with patch("app.services.payment.get_active_epay_config") as mock_config:
            mock_config.return_value = {
                "url": "https://pay.example.com",
                "pid": "1001",
                "key": "secret_key",
                "payment_type": "alipay",
                "notify_url": "https://example.com/notify",
                "return_url": "https://example.com/return",
            }

            order, payment_url = await create_payment_order(
                user_id="user-1",
                order_type="RECHARGE",
                amount=100.0,
                plan_id=None,
                payment_method="alipay",
                notify_url="https://example.com/notify",
                return_url="https://example.com/return",
                db=mock_db,
            )

            assert order is not None
            assert order.order_no is not None
            assert payment_url is not None

    @pytest.mark.asyncio
    async def test_create_payment_order_no_epay(self):
        """Test creating payment order without EPay config."""
        from app.services.payment import create_payment_order

        mock_db = AsyncMock()

        with patch("app.services.payment.get_active_epay_config") as mock_config:
            mock_config.return_value = None

            order, payment_url = await create_payment_order(
                user_id="user-1",
                order_type="RECHARGE",
                amount=100.0,
                plan_id=None,
                payment_method=None,
                notify_url="https://example.com/notify",
                return_url="https://example.com/return",
                db=mock_db,
            )

            assert order is not None
            assert payment_url is None

    @pytest.mark.asyncio
    async def test_mark_order_paid_recharge(self):
        """Test marking order as paid for recharge."""
        from app.services.payment import _mark_order_paid

        mock_db = AsyncMock()

        order = SimpleNamespace(
            id="order-1",
            order_no="ORD123",
            user_id="user-1",
            type="RECHARGE",
            amount=Decimal("100.00"),
            status="PENDING",
            payment_id=None,
            paid_at=None,
            payment_method="alipay",
        )

        user = SimpleNamespace(
            id="user-1",
            balance=Decimal("0.00"),
        )

        # Mock the user query
        mock_user_result = MagicMock()
        mock_user_result.scalar_one.return_value = user
        mock_db.execute.return_value = mock_user_result

        result = await _mark_order_paid(order, "PAYMENT-123", mock_db)

        assert result.status == "PAID"
        assert result.payment_id == "PAYMENT-123"
        assert user.balance == Decimal("100.00")
        # Verify db.add was called for Deposit
        mock_db.add.assert_called()

    @pytest.mark.asyncio
    async def test_mark_order_paid_already_paid(self):
        """Test marking already paid order returns unchanged."""
        from app.services.payment import _mark_order_paid

        mock_db = AsyncMock()

        order = SimpleNamespace(
            id="order-1",
            order_no="ORD123",
            user_id="user-1",
            type="RECHARGE",
            amount=Decimal("100.00"),
            status="PAID",
            payment_id="PAYMENT-OLD",
            paid_at=None,
        )

        result = await _mark_order_paid(order, "PAYMENT-NEW", mock_db)

        assert result.status == "PAID"
        assert result.payment_id == "PAYMENT-OLD"  # Unchanged

    @pytest.mark.asyncio
    async def test_mark_order_paid_invalid_status(self):
        """Test marking order with invalid status raises error."""
        from app.services.payment import _mark_order_paid

        mock_db = AsyncMock()

        order = SimpleNamespace(
            id="order-1",
            order_no="ORD123",
            user_id="user-1",
            type="RECHARGE",
            amount=Decimal("100.00"),
            status="CANCELLED",
            payment_id=None,
            paid_at=None,
        )

        with pytest.raises(ValueError, match="already processed"):
            await _mark_order_paid(order, "PAYMENT-123", mock_db)

    @pytest.mark.asyncio
    async def test_process_payment_callback(self):
        """Test processing payment callback."""
        from app.services.payment import process_payment_callback

        mock_db = AsyncMock()

        order = SimpleNamespace(
            id="order-1",
            order_no="ORD123",
            user_id="user-1",
            type="RECHARGE",
            amount=Decimal("100.00"),
            status="PENDING",
            payment_id=None,
            paid_at=None,
            payment_method="alipay",
        )

        user = SimpleNamespace(
            id="user-1",
            balance=Decimal("0.00"),
        )

        # First call returns order, second returns user
        mock_order_result = MagicMock()
        mock_order_result.scalar_one_or_none.return_value = order

        mock_user_result = MagicMock()
        mock_user_result.scalar_one.return_value = user

        mock_db.execute.side_effect = [mock_order_result, mock_user_result]

        result = await process_payment_callback("ORD123", "PAYMENT-123", mock_db)

        assert result is not None

    @pytest.mark.asyncio
    async def test_process_payment_callback_order_not_found(self):
        """Test processing callback for non-existent order."""
        from app.services.payment import process_payment_callback

        mock_db = AsyncMock()

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute.return_value = mock_result

        with pytest.raises(ValueError, match="Order not found"):
            await process_payment_callback("NONEXISTENT", "PAYMENT-123", mock_db)

    @pytest.mark.asyncio
    async def test_process_epay_callback_valid(self):
        """Test processing valid EPay callback."""
        from app.services.payment import _sign_epay_params, process_epay_callback

        mock_db = AsyncMock()

        # Build valid callback params
        params = {
            "pid": "1001",
            "trade_no": "EPAY123",
            "out_trade_no": "ORD123",
            "type": "alipay",
            "money": "100.00",
            "trade_status": "TRADE_SUCCESS",
        }

        # Sign the params
        sign = _sign_epay_params(params, "secret_key")
        params["sign"] = sign
        params["sign_type"] = "MD5"

        order = SimpleNamespace(
            id="order-1",
            order_no="ORD123",
            user_id="user-1",
            type="RECHARGE",
            amount=Decimal("100.00"),
            status="PENDING",
            payment_id=None,
            paid_at=None,
            payment_method="alipay",
        )

        user = SimpleNamespace(
            id="user-1",
            balance=Decimal("0.00"),
        )

        with patch("app.services.payment.get_active_epay_config") as mock_config:
            mock_config.return_value = {
                "url": "https://pay.example.com",
                "pid": "1001",
                "key": "secret_key",
                "payment_type": "alipay",
            }

            # Mock order and user queries
            mock_order_result = MagicMock()
            mock_order_result.scalar_one_or_none.return_value = order
            mock_user_result = MagicMock()
            mock_user_result.scalar_one.return_value = user
            mock_db.execute.side_effect = [mock_order_result, mock_user_result]

            result = await process_epay_callback(params, mock_db)

            assert result is not None

    @pytest.mark.asyncio
    async def test_process_epay_callback_invalid_sign(self):
        """Test processing EPay callback with invalid signature."""
        from app.services.payment import process_epay_callback

        mock_db = AsyncMock()

        params = {
            "pid": "1001",
            "trade_no": "EPAY123",
            "out_trade_no": "ORD123",
            "money": "100.00",
            "trade_status": "TRADE_SUCCESS",
            "sign": "invalid_signature",
            "sign_type": "MD5",
        }

        with patch("app.services.payment.get_active_epay_config") as mock_config:
            mock_config.return_value = {
                "url": "https://pay.example.com",
                "pid": "1001",
                "key": "secret_key",
            }

            with pytest.raises(ValueError, match="Invalid sign"):
                await process_epay_callback(params, mock_db)

    @pytest.mark.asyncio
    async def test_process_epay_callback_no_config(self):
        """Test processing EPay callback when config missing."""
        from app.services.payment import process_epay_callback

        mock_db = AsyncMock()

        with patch("app.services.payment.get_active_epay_config") as mock_config:
            mock_config.return_value = None

            with pytest.raises(ValueError, match="EPay is not configured"):
                await process_epay_callback({}, mock_db)

    @pytest.mark.asyncio
    async def test_process_epay_callback_missing_sign(self):
        """Test processing EPay callback with missing signature."""
        from app.services.payment import process_epay_callback

        mock_db = AsyncMock()

        with patch("app.services.payment.get_active_epay_config") as mock_config:
            mock_config.return_value = {
                "url": "https://pay.example.com",
                "pid": "1001",
                "key": "secret_key",
            }

            with pytest.raises(ValueError, match="Missing sign"):
                await process_epay_callback({}, mock_db)
