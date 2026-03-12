# Change Request: Query-to-Detail Order Consistency

## Issue Summary

When a user filters on the home page and clicks into an order, the detail page can appear inconsistent with what was queried (different context/UI or seemingly different order). This creates trust and usability issues for troubleshooting workflows.

## Observed Behavior

- Query page and detail page present different contextual information.
- Users may perceive they landed on a different order or different filter scope.
- The query form allows multiple filters simultaneously, but detail page does not show the originating query context.

## Technical Findings

1. Sales order filtering uses partial match (`contains`) rather than exact match:
   - This can return unintended orders if a partial value is entered.

2. Detail navigation only passes `sales_order`, `mode`, and `snapshot_date`; it does not carry full filter context.

3. Detail page uses a generic `Back` via `Referer`, but does not display source filters for user confirmation.

## Proposed Change

### A) Exact-match behavior for Sales Order

- If `sales_order` is provided, default to exact match (`==`) instead of partial `contains`.
- Optional future enhancement: add explicit "partial match" toggle for advanced search.

### B) Preserve and display query context on detail page

- Carry query params (`customer`, `material`, `plant`, `only_not_fully_on_request_date`, `page`, `page_size`) into order links.
- Show a context banner on detail page:
  - "Opened from query: SO=..., Customer=..., Material=..., Plant=..., Snapshot=..."

### C) UX clarity on mode/context

- Keep mode labels explicit (`Snapshot`, `Current`) and show selected snapshot version near header.
- Ensure `Back` returns user to the same filtered/paged list state.

## Acceptance Criteria

1. Entering full sales order `5000000039` returns only `5000000039` (unless partial mode is intentionally enabled).
2. Clicking order from filtered list opens matching detail page for same order.
3. Detail page shows originating filter context.
4. Clicking `Back` returns to the exact filtered list state (same filters, page, and page size).
5. Snapshot version remains consistent between list and detail.

## Test Plan

### FUT

- Query exact SO only -> click -> verify detail SO matches.
- Query SO + customer + material + plant -> click -> verify context banner and detail data.
- Use pagination + filters -> click -> back -> same page state retained.

### API/Behavior

- Validate filter logic for exact SO match.
- Validate no regression for customer/material/plant combined filtering.

## Notes

Screenshots provided during issue report:

- Query/list view screenshot
- Order detail screenshot

These should be attached to this change ticket for implementation validation.
