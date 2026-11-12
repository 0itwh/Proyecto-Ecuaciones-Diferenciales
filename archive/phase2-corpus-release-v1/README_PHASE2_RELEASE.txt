PHASE 2 CORPUS RELEASE V1

Contents:
- data_processed/l172_corpus: auxiliary quarantine corpus
- data_processed/l254_corpus: primary candidate corpus
- metadata: manifests and quality summaries
- logs: final reports and decision records
- scripts: reproducible builders when available

Reproduction order:
1. Run scripts/build_l172_relational_corpus.py
2. Run scripts/build_l254_relational_corpus.py
3. Run scripts/build_phase2_release_package.py

Scientific restriction:
Phase 3 may perform exploratory analysis only. Do not fit percolation models until measurement-condition decisions are explicitly updated.
