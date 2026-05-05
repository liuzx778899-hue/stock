# KLineChart Local Loading Fix

## Issue
#120

## Problem
CDN unpkg.com blocked by proxy. klinecharts.init() fails, causing dispose() TypeError.

## Fix
1. Download klinecharts.min.js to static/klinecharts.min.js
2. Change script src from CDN to /static/klinecharts.min.js

## Files
- templates/index.html (line 8)
- static/klinecharts.min.js (new)

## Acceptance
- [ ] KLineChart loads without error
- [ ] K-line chart renders correctly
- [ ] No TypeError on dispose()
