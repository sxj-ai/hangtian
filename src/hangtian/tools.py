"""Read-only tool backend for future harness integration; no Pi runner is implied."""
from __future__ import annotations
from .contracts import validate
from .data import DataError, Telemetry, digest, evaluate


class TelemetryTools:
    def __init__(self, data: Telemetry, public_task: dict, max_read_rows: int = 200):
        if data.entry["experiment_id"] != public_task["experiment_id"]:
            raise DataError("Task/source mismatch")
        self.data, self.task, self.max_read_rows = data, public_task, max_read_rows
        self.logs: list[dict] = []
        self.stopped = False

    def _window(self, window: dict) -> None:
        self.data.span(window)
        allowed = self.task["permitted_window"]
        if window["start_row"] < allowed["start_row"] or window["stop_row"] > allowed["stop_row"]:
            raise DataError("Window outside the task's permitted scope")

    def _channels(self, channels: list[str]) -> None:
        if not channels or set(channels) - set(self.task["channels"]):
            raise DataError("Channel outside the task's permitted scope")

    def call(self, name: str, arguments: dict) -> dict:
        if self.stopped:
            raise DataError("Task already submitted")
        if name not in self.task["tools"]:
            raise DataError("Tool not allowed")
        if name == "inspect_channels":
            if arguments:
                raise DataError("inspect_channels takes no arguments")
            result = self.task["channels"]
        elif name == "read_window":
            if set(arguments) != {"window", "channels"}:
                raise DataError("read_window requires exactly window and channels")
            window, channels = arguments["window"], arguments["channels"]
            self._window(window)
            self._channels(channels)
            rows = list(self.data.span(window))
            if len(rows) > self.max_read_rows:
                raise DataError("Read size cap exceeded; request smaller windows")
            origin = self.data.times[self.task["permitted_window"]["start_row"]]
            result = [{"row": i, "time_offset": self.data.times[i] - origin,
                       "values": {c: self.data.columns[c][i] for c in channels}} for i in rows]
        elif name in {"summarize_window", "compare_windows", "first_crossing"}:
            op = {"summarize_window": "stat", "compare_windows": "delta", "first_crossing": "first_crossing"}[name]
            if "op" in arguments:
                raise DataError("Operation is selected by the tool name, not by arguments")
            query = {"op": op, **arguments}
            validate("query", query)
            self._channels([query["channel"]])
            for key in ("window", "before", "after"):
                if key in query:
                    self._window(query[key])
            result = {"value": evaluate(self.data, query), "definition": query}
        elif name == "check_time_axis":
            if set(arguments) != {"window"}:
                raise DataError("check_time_axis requires exactly window")
            window = arguments["window"]
            self._window(window)
            rows = list(self.data.span(window))
            result = {"duplicate_count": evaluate(self.data, {"op": "duplicate_count", "window": window}),
                      "non_increasing_pairs": [[a, b] for a, b in zip(rows, rows[1:])
                                               if self.data.times[b] <= self.data.times[a]]}
        elif name == "submit_report":
            if set(arguments) != {"report"} or not isinstance(arguments["report"], dict):
                raise DataError("submit_report requires a report object")
            # Submission receipt is NOT a correctness verdict; do not expose private answers.
            self.stopped = True
            result = {"submitted": True, "correctness": "not_evaluated"}
        else:
            raise DataError("Unimplemented tool")
        record = {"tool": name, "arguments": arguments, "result": result, "source_sha256": self.data.sha256,
                  "observation_id": "OBS_" + digest([len(self.logs), name, arguments, result])[:20]}
        self.logs.append(record)
        return {"observation_id": record["observation_id"], "result": result}
