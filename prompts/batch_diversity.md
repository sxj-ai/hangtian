# Batch expansion policy

This policy applies to any batch size and dataset family. The requested slots
define private assessment coverage, not text to copy into the public question.
Use only the neutral environment and verified scalar anchors provided. Select
2-3 concise outcome criteria per task, normally referring to 2-6 relevant fact IDs.
An anchor is an example window, not a complete statement about the whole record.
Do not claim uniqueness, health, monotonic progression, equivalence, causal
compensation or physical service continuity from medians alone.

Keep the public task concrete: name the record scope and primary subsystem or
decision. Asking whether one record represents other records, whether an observed
behavior repeats, or whether reference data support a quantitative comparison is
allowed. Never put the answer, a required comparison technique, a channel checklist,
phase alignment instructions, required statistics or a multi-step recipe in the
public text. The problem's comparison objects are permissible scope; the method
for making them comparable remains the investigator's choice.

Tasks sharing an input may assess different outcomes, but avoid overlapping goals
within one pack. If reused across different experiments, acknowledge the same
assessment family privately. Do not describe parameterized instances as novel
task types or statistically independent samples. Separate representativeness,
phase dependence, multi-cycle evolution, observed subsystem participation and
reference suitability as appropriate; never demand every dimension in every task.

Write private rubrics that accept a justified negative result or a limited result
when warranted. Still require substantive source-specific evidence. Do not make
generic statements about missing topology a substitute for doing the analysis.
Do not prescribe physical mechanisms absent from the data. A task that asks about
measured availability must not require proof of physical uptime between samples.

If feedback is supplied, correct the underlying failure across affected tasks.
Return only the requested JSON object. Every public title and prompt must be your
new model output, not an assumed placeholder to be filled by the researcher.

## Mandatory public-interface revision (highest specificity)

For this reusable interface, the public prompt is exactly ONE short sentence,
at most 90 Chinese characters, containing only the investigation object/scope
and ONE requested outcome. Put NO supporting-analysis instructions after it.
Do not use channel identifiers (I_*, U_*, P_*), named lists of measured quantities,
parenthetical channel expansions, phase-code lists, or example phases. Naming
a subsystem such as Load2, a battery group, solar output, the bus, or BCR is
permitted when it defines the object of investigation.

Do NOT tell the agent to compare corresponding/matching phases, distinguish
active and inactive periods, check irradiation/temperature/current, or report
which branches are high/low. Those are consequential investigative choices.
Do NOT add clauses introduced by '需', '结合', '重点', '分别', '并说明',
'请说明', '避免', '而非' or '不得'. The generic response contract already
requires evidence and honest limitations. Do not place such clauses in titles.
Use at most 30 Chinese characters in the title. No lists or semicolons.

Reference suitability and repeatability are valid end goals, but specifying
the decisive matching controls is not. Phase dependence is a valid end goal,
but specifying phase labels/channels and ordering the phase comparison is not.
Do not presume a difference, anomaly, compensation, recovery, current absence,
measurement failure or explanation before the agent has inspected the data.

Keep the acronym BCR exactly as BCR in public text. Do not invent an expansion
or translate it into resistor, shunt, cycling resistor or load. In general,
never expand domain acronyms beyond the supplied verified channel dictionary.

Private output must also be concise: exactly TWO outcome criteria per task,
each <=70 Chinese characters and with 2-4 relevant fact IDs; each acceptable
alternatives statement <=50 Chinese characters. Exactly two consequential
decisions left to the agent, each <=45 Chinese characters. Distinctness <=60
Chinese characters. Private brevity must not introduce secret procedural
requirements. The assistant independently curates the final outcome rubric.

Do not center a public question on statistical independence when the data catalog
already declares the records to be cycles of the same experiment. Such a question
can be dismissed from metadata alone. Where the material supports it, investigate
the substantive information present in the measurements and its utility for an
operational judgment. Keep provenance limitations secondary to that data-dependent
goal. No presumption that the data are informative, missing, zero or repeated.
