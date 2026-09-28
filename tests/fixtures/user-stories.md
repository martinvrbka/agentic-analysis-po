# User stories — Order export

## US-01: Export orders
As an admin, I want to export orders, so that finance can reconcile.
Covers: DL-002
Scenario: Export succeeds
  Given 10 orders
  When I export
  Then I get a CSV with 10 rows
Scenario: Export fails
  Given the export fails
  When I look at the screen
  Then I see "Export failed, try again"
INVEST: I ✓ | N ✓ | V ✓ | E ✓ | S ✓ | T ✓
Slice: Walking skeleton

## US-02: Choose a date range
As an admin, I want to pick dates, so that the file is small.
Covers: DL-003
Scenario: Range applied
  Given orders in March and April
  When I pick March
  Then only March orders are exported
Scenario: Empty range
  Given no orders in May
  When I pick May
  Then I see "No orders in this range" (🔵 Open Question: offer an empty file too?)
INVEST: I ✗ (needs US-01) | N ✓ | V ✓ | E ✓ | S ✓ | T ✓
Slice: Walking skeleton

## US-03: See my last export
As an admin, I want to see when I last exported, so that I avoid duplicates.
Covers: DL-004
Scenario: Last export shown
  Given I exported yesterday
  When I open the export screen
  Then I see yesterday's date
Scenario: Never exported
  Given I never exported
  When I open the export screen
  Then I see "No exports yet"
INVEST: I ✓ | N ✓ | V ✓ | E ✓ | S ✗ | T ✓
Slice: Hardening

## Cross-cutting candidates for Definition of Done
- Exports are logged (DL-005)
