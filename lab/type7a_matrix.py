"""Native panel stimulus: keep USE's autoassignment on the intended track."""


def capture_target(session):
    """Select T1 before BUF capture; stock NORMAL input remains untouched."""
    destination = session.flex.destination
    if destination not in (1, 2, 3, 4):
        return False
    session.chord("TRK", "TRIG 1")
    return True


def recording_session(original, events):
    class TargetSession(original):
        def tap(self, name):
            if name == "SAMPLING":
                events.append(dict(destination=self.flex.destination,
                                   selected_t1=capture_target(self)))
            return super().tap(name)

    return TargetSession
