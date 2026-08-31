"""Broker Adapter Interface and Implementations.

Architecture:
Strategy Engine -> Execution Adapter -> Broker Adapter -> Broker API

Provides:
- BrokerAdapter abstract base class
- PaperBrokerAdapter (safe paper simulation & partial fill handling)
- FlattradeBrokerAdapter (Flattrade integration)
"""

from __future__ import annotations

import os
import uuid
from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any, Dict, List, Optional

from engine.calendar import format_timestamp_day
from engine.models import (
    OptionLeg,
    Order,
    OrderStatus,
    OptionType,
    TransactionType,
)


class BrokerAdapter(ABC):
    @abstractmethod
    def connect(self) -> bool:
        pass

    @abstractmethod
    def disconnect(self) -> bool:
        pass

    @abstractmethod
    def get_account(self) -> Dict[str, Any]:
        pass

    @abstractmethod
    def get_margins(self) -> Dict[str, float]:
        pass

    @abstractmethod
    def get_positions(self) -> List[Dict[str, Any]]:
        pass

    @abstractmethod
    def place_order(self, order: Order) -> Order:
        pass

    @abstractmethod
    def cancel_order(self, order_id: str) -> bool:
        pass

    @abstractmethod
    def get_order_status(self, order_id: str) -> OrderStatus:
        pass


class PaperBrokerAdapter(BrokerAdapter):
    """Safe Paper Trading Broker Adapter."""

    def __init__(self, initial_capital: float = 1_000_000.0):
        self.capital = initial_capital
        self.available_margin = initial_capital
        self.orders: Dict[str, Order] = {}
        self.is_connected = True

    def connect(self) -> bool:
        self.is_connected = True
        return True

    def disconnect(self) -> bool:
        self.is_connected = False
        return True

    def get_account(self) -> Dict[str, Any]:
        return {
            "broker": "Paper Simulation (Safe)",
            "account_id": "PAPER_1000000",
            "status": "ACTIVE_PAPER",
            "capital": self.capital,
            "available_margin": self.available_margin,
        }

    def get_margins(self) -> Dict[str, float]:
        return {
            "total_capital": self.capital,
            "available_margin": self.available_margin,
            "used_margin": self.capital - self.available_margin,
        }

    def get_positions(self) -> List[Dict[str, Any]]:
        return []

    def place_order(self, order: Order, fill_ratio: float = 1.0) -> Order:
        """
        Simulate order placement with support for partial fills.
        fill_ratio: 1.0 for full fill, 0.5 for 50% partial fill.
        """
        filled_qty = int(order.quantity * fill_ratio)
        order.filled_quantity = filled_qty
        order.remaining_quantity = order.quantity - filled_qty
        order.executed_price = order.requested_price

        if filled_qty == order.quantity:
            order.status = OrderStatus.FILLED
        elif filled_qty > 0:
            order.status = OrderStatus.PARTIAL
        else:
            order.status = OrderStatus.REJECTED

        self.orders[order.order_id] = order
        return order

    def cancel_order(self, order_id: str) -> bool:
        if order_id in self.orders:
            self.orders[order_id].status = OrderStatus.CANCELLED
            return True
        return False

    def get_order_status(self, order_id: str) -> OrderStatus:
        if order_id in self.orders:
            return self.orders[order_id].status
        return OrderStatus.FAILED
