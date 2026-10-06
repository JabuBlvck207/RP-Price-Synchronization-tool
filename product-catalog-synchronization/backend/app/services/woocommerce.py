"""
WooCommerce REST API client and synchronization service.

Supports:
- Price updates (regular + sale)
- Product creation
- Variation creation
- Status changes (publish / draft / private)
- Batch operations where the API allows

Auth: WooCommerce REST API keys (Consumer Key + Consumer Secret)
over HTTPS with query-string or Basic auth.
Docs: https://woocommerce.github.io/woocommerce-rest-api-docs/
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional
from urllib.parse import urljoin

import httpx

logger = logging.getLogger(__name__)


class WooProductStatus(str, Enum):
    PUBLISH = "publish"
    DRAFT = "draft"
    PRIVATE = "private"
    PENDING = "pending"


@dataclass
class WooConfig:
    """Connection settings for a WooCommerce store."""

    store_url: str  # e.g. https://mystore.com
    consumer_key: str
    consumer_secret: str
    api_version: str = "wc/v3"
    timeout: float = 60.0
    verify_ssl: bool = True

    def __post_init__(self):
        self.store_url = self.store_url.rstrip("/")

    @property
    def base_url(self) -> str:
        return f"{self.store_url}/wp-json/{self.api_version}/"


@dataclass
class SyncActionResult:
    """Result of a single product-level sync action."""

    sku: str
    action: str  # update_price | create_product | create_variation | update_status | skip
    success: bool
    woo_product_id: Optional[int] = None
    message: str = ""
    detail: Optional[dict] = None


@dataclass
class WooSyncReport:
    """Aggregate report for a full store sync run."""

    job_id: str
    prices_updated: int = 0
    products_created: int = 0
    variations_created: int = 0
    status_changed: int = 0
    skipped: int = 0
    errors: int = 0
    actions: list[SyncActionResult] = field(default_factory=list)

    def add(self, result: SyncActionResult) -> None:
        self.actions.append(result)
        if not result.success:
            self.errors += 1
            return
        if result.action == "update_price":
            self.prices_updated += 1
        elif result.action == "create_product":
            self.products_created += 1
        elif result.action == "create_variation":
            self.variations_created += 1
        elif result.action == "update_status":
            self.status_changed += 1
        elif result.action == "skip":
            self.skipped += 1

    def to_dict(self) -> dict[str, Any]:
        return {
            "job_id": self.job_id,
            "prices_updated": self.prices_updated,
            "products_created": self.products_created,
            "variations_created": self.variations_created,
            "status_changed": self.status_changed,
            "skipped": self.skipped,
            "errors": self.errors,
            "actions": [
                {
                    "sku": a.sku,
                    "action": a.action,
                    "success": a.success,
                    "woo_product_id": a.woo_product_id,
                    "message": a.message,
                }
                for a in self.actions
            ],
        }


class WooCommerceClient:
    """Low-level WooCommerce REST API client."""

    def __init__(self, config: WooConfig):
        self.config = config
        self._client: Optional[httpx.Client] = None

    def __enter__(self) -> "WooCommerceClient":
        self._client = httpx.Client(
            base_url=self.config.base_url,
            auth=(self.config.consumer_key, self.config.consumer_secret),
            timeout=self.config.timeout,
            verify=self.config.verify_ssl,
            headers={"Content-Type": "application/json", "User-Agent": "PCR-Platform/2.1"},
        )
        return self

    def __exit__(self, *args):
        if self._client:
            self._client.close()
            self._client = None

    def _request(
        self,
        method: str,
        path: str,
        *,
        params: Optional[dict] = None,
        json: Optional[dict | list] = None,
    ) -> dict | list:
        if not self._client:
            raise RuntimeError("Client not opened – use as context manager")
        path = path.lstrip("/")
        resp = self._client.request(method, path, params=params, json=json)
        if resp.status_code >= 400:
            try:
                body = resp.json()
                msg = body.get("message") or body.get("code") or resp.text
            except Exception:
                msg = resp.text
            raise WooCommerceAPIError(resp.status_code, msg, path)
        if resp.status_code == 204 or not resp.content:
            return {}
        return resp.json()

    # ------------------------------------------------------------------
    # Connection test
    # ------------------------------------------------------------------
    def test_connection(self) -> dict[str, Any]:
        """Verify credentials by fetching system status or products count."""
        try:
            data = self._request("GET", "system_status")
            return {
                "ok": True,
                "environment": data.get("environment", {}).get("version"),
                "store": self.config.store_url,
            }
        except WooCommerceAPIError:
            # system_status may require higher permissions – try products
            data = self._request("GET", "products", params={"per_page": 1})
            return {"ok": True, "store": self.config.store_url, "products_sample": len(data)}

    # ------------------------------------------------------------------
    # Products
    # ------------------------------------------------------------------
    def get_product_by_sku(self, sku: str) -> Optional[dict]:
        """Find a product (or variation parent) by SKU."""
        results = self._request("GET", "products", params={"sku": sku, "per_page": 5})
        if not results:
            return None
        # Prefer exact SKU match
        for p in results:
            if (p.get("sku") or "").strip().upper() == sku.strip().upper():
                return p
        return results[0] if results else None

    def get_product(self, product_id: int) -> dict:
        return self._request("GET", f"products/{product_id}")

    def update_product(self, product_id: int, data: dict) -> dict:
        return self._request("PUT", f"products/{product_id}", json=data)

    def create_product(self, data: dict) -> dict:
        return self._request("POST", "products", json=data)

    def update_product_prices(
        self,
        product_id: int,
        regular_price: Optional[str | float] = None,
        sale_price: Optional[str | float] = None,
    ) -> dict:
        payload: dict[str, Any] = {}
        if regular_price is not None:
            payload["regular_price"] = _price_str(regular_price)
        if sale_price is not None:
            # Empty string clears sale price in WC
            payload["sale_price"] = _price_str(sale_price) if sale_price != "" else ""
        return self.update_product(product_id, payload)

    def update_product_status(self, product_id: int, status: WooProductStatus | str) -> dict:
        st = status.value if isinstance(status, WooProductStatus) else status
        return self.update_product(product_id, {"status": st})

    # ------------------------------------------------------------------
    # Variations
    # ------------------------------------------------------------------
    def get_variations(self, product_id: int, per_page: int = 100) -> list[dict]:
        return self._request(
            "GET", f"products/{product_id}/variations", params={"per_page": per_page}
        )

    def get_variation_by_sku(self, parent_id: int, sku: str) -> Optional[dict]:
        variations = self.get_variations(parent_id)
        sku_up = sku.strip().upper()
        for v in variations:
            if (v.get("sku") or "").strip().upper() == sku_up:
                return v
        return None

    def create_variation(self, parent_id: int, data: dict) -> dict:
        return self._request("POST", f"products/{parent_id}/variations", json=data)

    def update_variation(self, parent_id: int, variation_id: int, data: dict) -> dict:
        return self._request(
            "PUT", f"products/{parent_id}/variations/{variation_id}", json=data
        )

    # ------------------------------------------------------------------
    # Batch (up to 100 items per request)
    # ------------------------------------------------------------------
    def batch_products(
        self,
        *,
        create: Optional[list[dict]] = None,
        update: Optional[list[dict]] = None,
        delete: Optional[list[int]] = None,
    ) -> dict:
        payload: dict[str, Any] = {}
        if create:
            payload["create"] = create
        if update:
            payload["update"] = update
        if delete:
            payload["delete"] = delete
        return self._request("POST", "products/batch", json=payload)


class WooCommerceAPIError(Exception):
    def __init__(self, status_code: int, message: str, path: str = ""):
        self.status_code = status_code
        self.message = message
        self.path = path
        super().__init__(f"WooCommerce API {status_code} on {path}: {message}")


def _price_str(value: str | float | int | None) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip()
    # Avoid scientific notation; WC expects decimal string
    return f"{float(value):.2f}".rstrip("0").rstrip(".") if float(value) != int(float(value)) else str(int(float(value)))


# ---------------------------------------------------------------------------
# High-level sync service – maps reconciliation results → WC actions
# ---------------------------------------------------------------------------
class WooCommerceSyncService:
    """
    Applies reconciliation outcomes to a live WooCommerce store.

    Safety rules (from platform spec):
    - Only confidently matched products get price updates
    - New products are created as draft by default (review before publish)
    - Unmatched / review-required products are never pushed automatically
    - Duplicate SKUs are skipped
    """

    def __init__(
        self,
        config: WooConfig,
        *,
        create_as_draft: bool = True,
        update_prices: bool = True,
        create_new_products: bool = False,
        unpublish_discontinued: bool = False,
        dry_run: bool = False,
    ):
        self.config = config
        self.create_as_draft = create_as_draft
        self.update_prices = update_prices
        self.create_new_products = create_new_products
        self.unpublish_discontinued = unpublish_discontinued
        self.dry_run = dry_run

    def sync_from_reconciliation(
        self,
        job_id: str,
        matches: list[Any],
        new_products: list[Any],
        discontinued: list[Any],
    ) -> WooSyncReport:
        """
        Drive store updates from a ReconciliationResult-like payload.

        `matches` items are expected to have:
          - supplier_product (sku, title, regular_price, sale_price, brand, ...)
          - woobe_product (optional)
          - status (PRICE_CHANGED, UNCHANGED, NEW, ...)
          - requires_review (bool)
        """
        report = WooSyncReport(job_id=job_id)

        with WooCommerceClient(self.config) as client:
            # 1. Price updates for confident matches
            if self.update_prices:
                for m in matches:
                    status = _attr(m, "status")
                    requires_review = _attr(m, "requires_review", False)
                    if requires_review:
                        report.add(
                            SyncActionResult(
                                sku=_sku(m),
                                action="skip",
                                success=True,
                                message="Skipped – requires human review",
                            )
                        )
                        continue
                    status_val = status.value if hasattr(status, "value") else str(status)
                    if status_val not in ("PRICE_CHANGED", "UNCHANGED", "EXISTING", "ACTIVE"):
                        continue
                    if status_val == "UNCHANGED":
                        report.add(
                            SyncActionResult(
                                sku=_sku(m),
                                action="skip",
                                success=True,
                                message="Price unchanged",
                            )
                        )
                        continue

                    result = self._update_price(client, m)
                    report.add(result)

            # 2. Create new products
            if self.create_new_products:
                for p in new_products:
                    result = self._create_product(client, p)
                    report.add(result)

            # 3. Optionally draft discontinued products
            if self.unpublish_discontinued:
                for p in discontinued:
                    result = self._unpublish(client, p)
                    report.add(result)

        return report

    def _update_price(self, client: WooCommerceClient, match: Any) -> SyncActionResult:
        supplier = _attr(match, "supplier_product")
        sku = _attr(supplier, "sku") or ""
        regular = _attr(supplier, "regular_price")
        sale = _attr(supplier, "sale_price")

        if not sku:
            return SyncActionResult(sku="", action="update_price", success=False, message="No SKU")

        if self.dry_run:
            return SyncActionResult(
                sku=sku,
                action="update_price",
                success=True,
                message=f"[dry-run] Would set regular={regular}, sale={sale}",
            )

        try:
            product = client.get_product_by_sku(sku)
            if not product:
                return SyncActionResult(
                    sku=sku,
                    action="update_price",
                    success=False,
                    message="Product not found in WooCommerce by SKU",
                )

            pid = product["id"]
            # If this is a variation, update via parent
            parent_id = product.get("parent_id") or 0
            if parent_id and product.get("type") == "variation":
                data: dict[str, Any] = {}
                if regular is not None:
                    data["regular_price"] = _price_str(regular)
                if sale is not None:
                    data["sale_price"] = _price_str(sale) if sale != "" else ""
                client.update_variation(parent_id, pid, data)
            else:
                client.update_product_prices(pid, regular_price=regular, sale_price=sale)

            return SyncActionResult(
                sku=sku,
                action="update_price",
                success=True,
                woo_product_id=pid,
                message=f"Updated prices regular={regular}, sale={sale}",
            )
        except WooCommerceAPIError as e:
            logger.warning("Price update failed for %s: %s", sku, e)
            return SyncActionResult(
                sku=sku,
                action="update_price",
                success=False,
                message=str(e),
            )

    def _create_product(self, client: WooCommerceClient, product: Any) -> SyncActionResult:
        sku = _attr(product, "sku") or ""
        title = _attr(product, "title") or sku or "Untitled"
        regular = _attr(product, "regular_price")
        sale = _attr(product, "sale_price")
        brand = _attr(product, "brand")

        if not sku:
            return SyncActionResult(sku="", action="create_product", success=False, message="No SKU")

        if self.dry_run:
            return SyncActionResult(
                sku=sku,
                action="create_product",
                success=True,
                message=f"[dry-run] Would create '{title}'",
            )

        try:
            # Avoid duplicates
            existing = client.get_product_by_sku(sku)
            if existing:
                return SyncActionResult(
                    sku=sku,
                    action="skip",
                    success=True,
                    woo_product_id=existing["id"],
                    message="Already exists in WooCommerce",
                )

            payload: dict[str, Any] = {
                "name": title,
                "type": "simple",
                "sku": sku,
                "status": "draft" if self.create_as_draft else "publish",
                "regular_price": _price_str(regular) if regular is not None else "",
            }
            if sale is not None:
                payload["sale_price"] = _price_str(sale)
            if brand:
                # Brands are often a custom taxonomy or attribute – store as meta for MVP
                payload["meta_data"] = [{"key": "brand", "value": brand}]

            created = client.create_product(payload)
            return SyncActionResult(
                sku=sku,
                action="create_product",
                success=True,
                woo_product_id=created.get("id"),
                message=f"Created as {payload['status']}",
            )
        except WooCommerceAPIError as e:
            logger.warning("Create product failed for %s: %s", sku, e)
            return SyncActionResult(
                sku=sku,
                action="create_product",
                success=False,
                message=str(e),
            )

    def _unpublish(self, client: WooCommerceClient, product: Any) -> SyncActionResult:
        sku = _attr(product, "sku") or ""
        if not sku:
            return SyncActionResult(sku="", action="update_status", success=False, message="No SKU")

        if self.dry_run:
            return SyncActionResult(
                sku=sku,
                action="update_status",
                success=True,
                message="[dry-run] Would set status=draft",
            )

        try:
            existing = client.get_product_by_sku(sku)
            if not existing:
                return SyncActionResult(
                    sku=sku,
                    action="skip",
                    success=True,
                    message="Not found in WooCommerce – nothing to unpublish",
                )
            client.update_product_status(existing["id"], WooProductStatus.DRAFT)
            return SyncActionResult(
                sku=sku,
                action="update_status",
                success=True,
                woo_product_id=existing["id"],
                message="Set to draft (potentially discontinued)",
            )
        except WooCommerceAPIError as e:
            return SyncActionResult(
                sku=sku,
                action="update_status",
                success=False,
                message=str(e),
            )


def _attr(obj: Any, name: str, default: Any = None) -> Any:
    if obj is None:
        return default
    if isinstance(obj, dict):
        return obj.get(name, default)
    return getattr(obj, name, default)


def _sku(match: Any) -> str:
    supplier = _attr(match, "supplier_product")
    return (_attr(supplier, "sku") or "") if supplier else ""
