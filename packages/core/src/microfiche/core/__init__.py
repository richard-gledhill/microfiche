"""microfiche core: scanning, classification, filing, and library management logic.

See docs/development/architecture.md for the architecture this package implements.
"""

import logging

# Add a NullHandler to the logger so it doesn't emit logs by default
logging.getLogger(__name__).addHandler(logging.NullHandler())
