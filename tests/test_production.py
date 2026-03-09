"""Tests for the production service.

Test cases to implement:
1. Start production with valid recipe
2. Reject recipe not belonging to building type
3. Tick advances progress by 1
4. Completion consumes inputs and creates outputs
5. Low satisfaction halves progress rate
6. Insufficient inputs at completion pauses building
7. Build building deducts credits and materials
8. Build building with insufficient funds fails
"""
