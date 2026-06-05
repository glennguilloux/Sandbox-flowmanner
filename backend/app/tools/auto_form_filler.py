"""
Browser Automation Tools — Auto Form Filler.

auto_form_filler → Automatically detect input fields on a page and fill
    them with intelligent defaults or user-provided data.
"""

from __future__ import annotations

import logging

from pydantic import Field

from app.tools.base import BaseTool, ToolInput, ToolMetadata, ToolResult, register_tool

logger = logging.getLogger(__name__)

# ── Heuristic field → value mappings ──────────────────────────────────

# Common form field name/label patterns and their auto-fill values
_FIELD_MAPPINGS: dict[str, str] = {
    # Name fields
    "first_name": "John",
    "last_name": "Doe",
    "full_name": "John Doe",
    "name": "John Doe",
    "firstname": "John",
    "lastname": "Doe",
    "fname": "John",
    "lname": "Doe",
    # Email
    "email": "user@example.com",
    "email_address": "user@example.com",
    "e-mail": "user@example.com",
    "mail": "user@example.com",
    # Phone
    "phone": "+1-555-0123",
    "telephone": "+1-555-0123",
    "mobile": "+1-555-0123",
    "tel": "+1-555-0123",
    "phone_number": "+1-555-0123",
    "cell": "+1-555-0123",
    # Address
    "address": "123 Main Street",
    "street": "123 Main Street",
    "street_address": "123 Main Street",
    "address1": "123 Main Street",
    "address_1": "123 Main Street",
    "address_line1": "123 Main Street",
    "address2": "Apt 4B",
    "address_line2": "Apt 4B",
    "city": "San Francisco",
    "town": "San Francisco",
    "state": "CA",
    "province": "ON",
    "region": "CA",
    "zip": "94105",
    "zipcode": "94105",
    "zip_code": "94105",
    "postal": "94105",
    "postal_code": "94105",
    "postcode": "94105",
    "country": "US",
    # Organization
    "company": "Acme Corp",
    "organization": "Acme Corp",
    "org": "Acme Corp",
    "business": "Acme Corp",
    "company_name": "Acme Corp",
    # Job
    "job_title": "Software Engineer",
    "title": "Software Engineer",
    "occupation": "Software Engineer",
    "position": "Software Engineer",
    "role": "Software Engineer",
    # Website
    "website": "https://example.com",
    "url": "https://example.com",
    "blog": "https://example.com",
    "homepage": "https://example.com",
    # Username
    "username": "johndoe",
    "user": "johndoe",
    "login": "johndoe",
    "user_id": "johndoe",
    "nickname": "johndoe",
    # Password
    "password": "P@ssw0rd!2024",
    "passwd": "P@ssw0rd!2024",
    "pwd": "P@ssw0rd!2024",
    "pass": "P@ssw0rd!2024",
    "confirm_password": "P@ssw0rd!2024",
    # Dates
    "date": "2024-01-15",
    "birthdate": "1990-06-15",
    "dob": "1990-06-15",
    "birthday": "1990-06-15",
    "start_date": "2024-01-01",
    "end_date": "2024-12-31",
    "date_of_birth": "1990-06-15",
    # Numbers
    "age": "30",
    "quantity": "1",
    "amount": "100",
    "price": "49.99",
    "budget": "5000",
    # Text areas
    "message": "This is an automated test message.",
    "comment": "This is an automated test comment.",
    "description": "Automated form fill test description.",
    "bio": "Experienced professional with a passion for technology.",
    "notes": "Automated test notes.",
    "feedback": "Great product! Automated test feedback.",
    # Search
    "search": "test query",
    "query": "test query",
    "q": "test query",
    "keyword": "test query",
    # Subject
    "subject": "Automated Test Subject",
    "topic": "Automated Test Topic",
    # URL/slug
    "slug": "test-page",
    "permalink": "test-page",
}

# Field name patterns that should be left empty (too sensitive or context-specific)
_SKIP_FIELDS: set[str] = {
    "captcha", "recaptcha", "2fa", "mfa", "totp", "security_code",
    "verification_code", "otp", "pin", "credit_card", "card_number",
    "cvv", "cvc", "ssn", "social_security", "tax_id",
    "current_password", "old_password", "existing_password",
    "reset_token", "confirmation_token",
}


# ── Input ─────────────────────────────────────────────────────────────

class AutoFormFillerInput(ToolInput):
    action: str = Field(
        "fill",
        description="Action: 'fill' (auto-detect and fill fields), 'preview' (show what would be filled without executing)",
    )
    data: dict[str, str] | None = Field(
        None,
        description="Explicit field name → value overrides (takes precedence over heuristics)",
    )
    url: str | None = Field(
        None,
        description="URL to navigate to before filling (optional — assumes already on page if omitted)",
    )
    strategy: str = Field(
        "heuristic",
        description="Fill strategy: 'heuristic' (pattern matching) or 'llm' (AI-powered field detection)",
    )
    submit: bool = Field(
        False,
        description="Submit the form after filling all fields",
    )
    max_fields: int = Field(
        30,
        ge=1,
        le=100,
        description="Maximum number of fields to fill",
    )


# ── Tool ──────────────────────────────────────────────────────────────

class AutoFormFillerTool(BaseTool):
    """Detect and automatically fill web forms using heuristics or LLM."""

    def __init__(self):
        metadata = ToolMetadata(
            tool_id="auto_form_filler",
            name="Auto Form Filler",
            description=(
                "Automatically detect input fields on web pages and fill them "
                "with intelligent defaults based on field labels and names."
            ),
            category="browser-automation",
            input_schema=AutoFormFillerInput.schema_extra(),
            output_schema={
                "type": "object",
                "properties": {
                    "result": {"type": "object"},
                    "success": {"type": "boolean"},
                },
            },
            tags=["browser", "forms", "automation", "differentiator"],
            requires_auth=True,
            timeout_seconds=30,
        )
        super().__init__(metadata=metadata)

    # ── execute ──────────────────────────────────────────────────

    async def execute(self, input_data: dict) -> ToolResult:
        from app.services.browser_manager import get_browser_manager
        from app.services.browser_service import get_browser_service

        try:
            validated = AutoFormFillerInput(**input_data)
        except Exception as e:
            return ToolResult.error_result(
                tool_id=self.tool_id, error=f"Invalid input: {e}"
            )

        context = input_data.get("context")
        if not context:
            return ToolResult.error_result(
                tool_id=self.tool_id, error="No context provided"
            )

        user_id = context.get("user_id")
        if not user_id:
            return ToolResult.error_result(
                tool_id=self.tool_id, error="No user_id in context"
            )

        uid = str(user_id)
        service = get_browser_service()
        manager = get_browser_manager()

        # Navigate if URL provided
        if validated.url:
            nav = await service.navigate(uid, validated.url)
            if not nav.get("success"):
                return ToolResult.error_result(
                    tool_id=self.tool_id,
                    error=f"Navigation failed: {nav.get('error')}",
                )

        session = manager.get_user_session(uid)
        if not session or not session.is_active():
            return ToolResult.error_result(
                tool_id=self.tool_id, error="No active browser session"
            )

        try:
            # Detect form fields via JavaScript
            fields = await self._detect_fields(session)

            if not fields:
                return ToolResult.success_result(
                    tool_id=self.tool_id,
                    result={
                        "action": validated.action,
                        "fields_found": 0,
                        "fields_filled": 0,
                        "message": "No fillable fields detected on the page",
                    },
                )

            # Resolve values for each field
            overrides = validated.data or {}
            resolved = self._resolve_values(fields, overrides, validated.max_fields)

            if validated.action == "preview":
                session.touch()
                return ToolResult.success_result(
                    tool_id=self.tool_id,
                    result={
                        "action": "preview",
                        "fields_found": len(fields),
                        "fields_previewed": len(resolved),
                        "fields": resolved,
                    },
                )

            # Fill the fields
            filled = await self._fill_fields(session, resolved, validated.submit)
            session.touch()

            return ToolResult.success_result(
                tool_id=self.tool_id,
                result={
                    "action": "fill",
                    "fields_found": len(fields),
                    "fields_filled": len(filled),
                    "submitted": validated.submit,
                    "fields": filled,
                },
            )
        except Exception as e:
            logger.exception("auto_form_filler failed")
            return ToolResult.error_result(tool_id=self.tool_id, error=str(e))

    # ── detect_fields ───────────────────────────────────────────

    async def _detect_fields(self, session) -> list[dict]:
        """Use JavaScript to find all form input fields on the page."""
        script = """
        () => {
            const fields = [];
            const inputs = document.querySelectorAll(
                'input:not([type="hidden"]):not([type="submit"]):not([type="button"]):not([type="reset"]):not([type="image"]), ' +
                'textarea, select, [contenteditable="true"]'
            );
            inputs.forEach((el, idx) => {
                // Find associated label
                let label = '';
                if (el.id) {
                    const labelEl = document.querySelector('label[for="' + el.id + '"]');
                    if (labelEl) label = labelEl.textContent.trim();
                }
                if (!label && el.closest('label')) {
                    label = el.closest('label').textContent.trim();
                }
                if (!label && el.getAttribute('aria-label')) {
                    label = el.getAttribute('aria-label');
                }
                if (!label && el.getAttribute('placeholder')) {
                    label = el.getAttribute('placeholder');
                }
                if (!label && el.name) {
                    label = el.name.replace(/[_-]/g, ' ');
                }

                // Get attributes
                const attrs = {};
                for (const attr of el.attributes) {
                    attrs[attr.name] = attr.value;
                }

                // Generate a CSS selector
                let selector = '';
                if (el.id) selector = '#' + el.id;
                else if (el.name) selector = el.tagName.toLowerCase() + '[name="' + el.name + '"]';
                else if (el.className && typeof el.className === 'string') {
                    selector = el.tagName.toLowerCase() + '.' + el.className.split(' ')[0];
                }

                fields.push({
                    index: idx,
                    tag: el.tagName.toLowerCase(),
                    type: el.type || 'text',
                    name: el.name || '',
                    id: el.id || '',
                    label: label.substring(0, 100),
                    placeholder: el.placeholder || '',
                    selector: selector,
                    required: el.required || false,
                    value: el.value || '',
                });
            });
            return fields;
        }
        """
        try:
            return await session.page.evaluate(f"({script})()")
        except Exception:
            return []

    # ── resolve_values ──────────────────────────────────────────

    def _resolve_values(
        self,
        fields: list[dict],
        overrides: dict[str, str],
        max_fields: int,
    ) -> list[dict]:
        """Map detected fields to fill values using heuristics and overrides."""
        resolved = []
        count = 0

        for field in fields:
            if count >= max_fields:
                break

            name = field.get("name", "").lower()
            label = field.get("label", "").lower()
            placeholder = field.get("placeholder", "").lower()
            field_id = field.get("id", "").lower()
            field_type = field.get("type", "text")

            # Check all identifiers for skip patterns
            identifiers = f"{name} {label} {placeholder} {field_id}"
            if any(skip in identifiers for skip in _SKIP_FIELDS):
                continue

            # Skip password fields by default (security)
            if field_type == "password":
                # Only fill if explicitly in overrides
                matched_override = None
                for key, val in overrides.items():
                    if key.lower() in identifiers:
                        matched_override = val
                        break
                if matched_override:
                    resolved.append({**field, "fill_value": matched_override, "method": "override"})
                    count += 1
                continue

            # Skip select/radio/checkbox — they need special handling
            if field.get("tag") in ("select",) or field_type in ("radio", "checkbox"):
                # Only fill if explicitly in overrides
                matched_override = None
                for key, val in overrides.items():
                    if key.lower() in identifiers:
                        matched_override = val
                        break
                if matched_override:
                    resolved.append({**field, "fill_value": matched_override, "method": "override"})
                    count += 1
                continue

            # Check explicit overrides first
            matched = False
            for key, val in overrides.items():
                if key.lower() in identifiers:
                    resolved.append({**field, "fill_value": val, "method": "override"})
                    matched = True
                    count += 1
                    break
            if matched:
                continue

            # Try heuristic matching
            value, method = self._heuristic_match(name, label, placeholder, field_id)
            if value is not None:
                resolved.append({**field, "fill_value": value, "method": method})
                count += 1

        return resolved

    def _heuristic_match(
        self, name: str, label: str, placeholder: str, field_id: str,
    ) -> tuple[str | None, str]:
        """Match a field to a fill value using keyword matching."""
        # Build a search text from all identifiers
        search_parts = [name, label, placeholder, field_id]
        search = " ".join(p for p in search_parts if p)

        # Remove common suffixes
        for suffix in ["_input", "_field", "_ctrl", "_control"]:
            search = search.replace(suffix, "")

        # Try exact key matches first
        normalized = search.replace(" ", "_").replace("-", "_").strip("_")
        if normalized in _FIELD_MAPPINGS:
            return _FIELD_MAPPINGS[normalized], "exact"

        # Try partial matches — longest key first to prioritize specific matches
        for key in sorted(_FIELD_MAPPINGS, key=len, reverse=True):
            if key in search:
                return _FIELD_MAPPINGS[key], f"keyword:{key}"

        # Try word-by-word matching
        words = search.replace("_", " ").replace("-", " ").split()
        for word in words:
            if word in _FIELD_MAPPINGS:
                return _FIELD_MAPPINGS[word], f"word:{word}"

        return None, ""

    # ── fill_fields ─────────────────────────────────────────────

    async def _fill_fields(
        self,
        session,
        resolved: list[dict],
        submit: bool,
    ) -> list[dict]:
        """Fill the detected fields with resolved values."""
        results = []

        for field in resolved:
            selector = field.get("selector", "")
            fill_value = field.get("fill_value", "")

            if not selector:
                results.append({**field, "filled": False, "error": "No selector"})
                continue

            try:
                # Try to fill using Playwright
                handle = await session.page.query_selector(selector)
                if handle:
                    await handle.fill(str(fill_value))
                    results.append({**field, "filled": True, "fill_value": fill_value})
                else:
                    results.append({**field, "filled": False, "error": "Element not found"})
            except Exception as e:
                results.append({**field, "filled": False, "error": str(e)})

        # Submit if requested and at least one field was filled
        if submit and any(r.get("filled") for r in results):
            await session.page.keyboard.press("Enter")

        return results


# ── Register ──────────────────────────────────────────────────────────

register_tool(AutoFormFillerTool())
