"""Decision recorder — Phase 170: DB persistence."""

from database.repositories.decision_persistor import DecisionPersistor
from database.connection import get_session


class DecisionRecorder:
    def __init__(self):
        self.session = get_session()
        self.persistor = DecisionPersistor(self.session)

    def record(self, event) -> None:
        self.persistor.persist(event)
