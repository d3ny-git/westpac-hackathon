"""Customer Guardian JSON API for the GEL React UI (web/).

A thin FastAPI layer over the EXISTING, tested node functions: every endpoint calls a function
from nodes/, agent.py or scripts/load_fixtures.py and only reshapes its result for the screen.
No business rules live here. Run it with `python app.py` (127.0.0.1:8600).
"""
