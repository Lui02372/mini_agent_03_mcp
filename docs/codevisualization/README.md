# Architecture evidence

Open index.html locally. architecture.json describes deployment and runtime
connections verified against the referenced code. The static extractor lists
Python files but does not infer Python imports; files.mmd is not a runtime call
graph. Hidden .github files are excluded by its scan and are explicitly cited
by the architecture definition. Database connectivity is conditional on the
external server firewall and is not established by this graph.

Generated using the codevisualization skill's `generate(project, output,
architecture)` export. HTML interaction has not been browser-tested.
