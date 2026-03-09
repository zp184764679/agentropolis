"""Tests for the market matching engine.

Test cases to implement:
1. Basic buy-sell match at midpoint price
2. Price priority: lower sell matched first
3. Time priority: earlier order matched first at same price
4. Partial fill: large buy matched against smaller sell
5. No match: buy price < sell price
6. Cancel order: balance/inventory unreserved
7. Self-trade prevention: same company buy+sell don't match
8. Multiple resources independent matching
9. Property-based: balance conservation (buyer_debit == seller_credit)
10. Property-based: no negative inventory after matching
"""
