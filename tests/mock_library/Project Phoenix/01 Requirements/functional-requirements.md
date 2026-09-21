# Project Phoenix — Functional Requirements

## Overview

This document captures the functional requirements for Project Phoenix, gathered from
stakeholder interviews during the discovery phase.

## User Stories

- As a warehouse operator, I want to scan a pallet barcode so that its contents are
  logged automatically.
- As a shift supervisor, I want a live dashboard of throughput so that I can spot
  bottlenecks before they cause delays.

## Acceptance Criteria

- Barcode scans are recorded within 500ms and appear on the dashboard without a manual
  refresh.
- The system rejects a scan for a pallet ID that doesn't exist in the current shipment
  manifest, with a clear on-screen error.
