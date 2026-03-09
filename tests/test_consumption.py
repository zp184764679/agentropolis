"""Tests for the consumption service.

Test cases to implement:
1. Full supply: satisfaction recovers toward 100
2. No RAT: satisfaction drops by decay rate
3. No DW: satisfaction drops by decay rate
4. Both missing: satisfaction drops
5. Partial supply: proportional penalty
6. Zero satisfaction: workers lost (attrition)
7. Low satisfaction: productivity modifier returned
8. Property-based: total consumed <= total available
"""
