# Resource catalog fixtures

This folder contains synthetic data used to exercise the same import and
matching contracts that production course and mentor catalogs use.

- `synthetic-courses.csv`: 10 fictional course fixtures.
- `synthetic-mentors.csv`: 12 fictional, non-contactable mentor fixtures.

Every fixture is explicitly marked `data_class=synthetic_fixture` and
`simulation_only=true`. The records do not describe real people, organizations,
or live courses. Do not replace the disclosure labels with real-looking contact
details.

For real data, start from the empty CSV files in the repository `templates/`
directory. Preserve source, consent, conflict, availability, validity, and
update fields. Run the complete test suite before connecting a new catalog.
