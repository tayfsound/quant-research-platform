from pathlib import Path

p = Path("services/decision_recorder.py")
t = p.read_text()

old = '''class DecisionRecorder:
 def __init__(self, storage_path=None):
 self.storage_path = Path(storage_path) if storage_path else Path("decision_logs")
 self.storage_path.mkdir(parents=True, exist_ok=True)
 self.session = get_session()
 self.persistor = DecisionPersistor(self.session)'''

new = '''class DecisionRecorder:
 def __init__(self, storage_path=None):
 self.storage_path = Path(storage_path) if storage_path else None
 if self.storage_path:
 self.storage_path.mkdir(parents=True, exist_ok=True)
 self.session = get_session()
 self.persistor = DecisionPersistor(self.session)'''

t = t.replace(old, new)

old2 = ''' self.persistor.persist(event)

 log_file = self.storage_path / f"decision_{event.id}.json"
 log_file.write_text(event.model_dump_json(indent=2))

 return event'''

new2 = ''' self.persistor.persist(event)

 if self.storage_path:
 log_file = self.storage_path / f"decision_{event.id}.json"
 log_file.write_text(event.model_dump_json(indent=2))

 return event'''

t = t.replace(old2, new2)
p.write_text(t)
print("flat-file opt-in")
