# Sales Order Schedule Troubleshooter POC - Management One-Pager

## Executive Overview

This proof of concept (POC) demonstrates a lightweight web application that explains why SAP sales order schedule dates were confirmed, delayed, or left unscheduled. It is designed for S/4HANA-style ATP/AATP analysis and combines supply, allocation, delivery, planned order, BOP context, and plant-substitution signals into clear reason outputs for each schedule line.

## Problem Addressed

Teams currently spend significant time manually tracing schedule outcomes across multiple SAP objects and logs. That process is slow, inconsistent, and difficult to scale for customer-facing commitments. The POC provides a single view with deterministic reasoning and evidence to reduce investigation effort.

## What the POC Delivers

- Search by sales order, customer, material, and plant
- Snapshot-based schedule analysis with deterministic reason trace
- Multi-factor reason trace (primary + contributing reasons)
- Visual flags for unscheduled and delayed schedules
- Read-only raw dataset inspection for audit and transparency
- Snapshot support workflow via `Email PLPC Support` with human-readable prefilled details
- Stable one-command start/restart operations for fast redeploy
- Cloud deployment path from GitHub to Render with public share URL

## Data Scope in POC

The POC runs on flat-file datasets (50 order headers plus related item/schedule/supply/allocation/delivery/planned/BOP/substitution files). This allows rapid testing without production integration dependencies while preserving realistic ATP/BOP troubleshooting patterns.

## Business Value

- Faster root-cause analysis for order-date questions
- Better consistency in schedule-date explanation across teams
- Reduced support cycle time for PLPC and order management
- Higher confidence in customer communication on delays/availability
- Better readiness for future AATP analytics and automation

## Possible Use Cases

1. **Order Escalation Triage**
   - Quickly explain why a specific order was delayed or unscheduled.
2. **Daily Backlog Review**
   - Identify no-schedule and delayed clusters by customer/material.
3. **PLPC Support Handoff**
   - Send structured snapshot details directly from the order screen.
4. **Allocation and Supply Pattern Review**
   - Validate whether allocation exhaustion or source-supply gaps are driving outcomes.
5. **BOP Outcome Validation**
   - Validate BOP context is reflected without exposing `BOP_FAILED` as a final reason.
6. **Training and Process Standardization**
   - Use deterministic reason outputs as a common troubleshooting playbook.

## Limitations of Current POC

- No live SAP integration yet (no direct RFC/OData reads)
- No role-based access control
- No persistent historical data store beyond current flat files

## Deployment Readiness Note

- Public cloud endpoint target: `https://sales-order-poc.onrender.com/`
- Runtime compatibility requires Python `3.12.8` (configured in `render.yaml` and `runtime.txt`)
- If deployment fails with `pydantic-core`/`maturin` build errors, run Render **Manual Deploy** with **Clear build cache & deploy**

## Recommended Next Steps

1. Pilot with a selected PLPC/support analyst group.
2. Capture accuracy and time-to-resolution metrics against current process.
3. Integrate with SAP data sources (read-only first) and automate refresh.
4. Add role-based access and environment hardening for broader rollout.
5. Define production support model and ownership for rule governance.
