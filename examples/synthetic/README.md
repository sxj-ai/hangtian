# Synthetic fixture — NOT XJTU-SPS

The 60 rows were authored solely for deterministic software tests. They contain a power/current level change, a temperature spike, a repeated timestamp, and a selected-channel zero run. The context signal is also synthetic. They are not observations from a real spacecraft or from the user's HPC.

Units are deliberately null to test that models must not invent them. The fixture does not establish a physical cause, represent a validated simulator, or measure any LLM's performance. `MockModel` responses are handwritten contract fixtures. See the repository running guide for the offline command.
