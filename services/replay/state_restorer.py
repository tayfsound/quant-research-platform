from contracts.replay.replay_snapshot import ReplaySnapshot


class ReplayStateRestorer:

    def restore(self, data: dict) -> ReplaySnapshot:

        return ReplaySnapshot(
            snapshot_id=data["snapshot_id"],
            created_at=data["created_at"],
            decision_event_id=data.get(
                "decision_event_id",
                ""
            ),
            market_state=data.get(
                "market_state",
                {}
            ),
            risk_state=data.get(
                "risk_state",
                {}
            ),
            belief_state=data.get(
                "belief_state",
                data.get("beliefs", {})
            ),
            beliefs=data.get(
                "beliefs",
                data.get("belief_state", {})
            ),
            weight_snapshot_id=data.get(
                "weight_snapshot_id"
            ),
            decision_hash=data.get(
                "decision_hash",
                ""
            ),
        )
