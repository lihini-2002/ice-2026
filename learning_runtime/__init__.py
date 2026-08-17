"""Real-time coaching runtime for the craft-learning app.

Separate from the offline authoring pipeline in scripts/ — no dependency on
projectaria-tools or VRS files. Consumes step_templates.json (written by
scripts/generate_step_templates.py) and a stream of perception output from a
top-mounted RGB camera on the learner side.

See README.md for the module map, the offline-first testing workflow
(run_offline_test.py), and which step_templates.json fields require
human/artisan input that this runtime cannot supply on its own.
"""
