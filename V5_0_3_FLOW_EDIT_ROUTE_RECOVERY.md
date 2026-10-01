# v5.0.3 — Flow edit-route recovery

Fixes a Flow still-generation failure where AutoVideoAI could remain on a generated-media detail URL such as:

`https://flow.google.com/project/<uuid>/edit/<asset-id>`

That page contains prompt-like/settings controls but is not the project generation composer. Older code could therefore classify it as the standard editor and look for a `generate_button` that does not exist.

v5.0.3:

- never treats `/edit/` as a valid project composer;
- normalizes back to the canonical `/project/<uuid>` route before detecting editor mode;
- recovers the project page in the existing browser context if normal return fails;
- refuses to submit an image prompt while still on an `/edit/` page;
- includes the corrupt-frame recovery from v5.0.1 and the iterative director splitter from v5.0.2.
