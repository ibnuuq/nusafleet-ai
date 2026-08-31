# eval/questions/

Placeholder. This will hold the runtime-facing question bank fed to agents
during evaluation (M14). It contains **questions only** -- no expected
answers, no SQL, no scoring keys. Ground truth for these questions lives in
`eval/reference/` and must never be merged into this folder or into anything
an agent can read.
