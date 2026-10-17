# Development GUI generation and identification: hardware coverage

Recorded 2026-10-18 (Asia/Seoul). These are user-operated trials on one HHKB
PD-KB800W. GUI screenshots, user functional confirmations and local generated
file/manifest hashes are separate evidence. No additional device commands were
performed while recording these results.

| Build | Recipe | Confirmed scope |
|---|---|---|
| B33E6ADF, RT-only, Development | Golden R32/P32, approximately 0.053 mm each | GUI generation/install; 4960/4960 progress; reconnect PASS; metadata/catalog + local record match; ordinary typing and Observer confirmed by user |
| A96B4BA0, HOLD, Development | SPACE tap / FN hold, 250 ms, one slot | GUI generation/validation/install; flash PASS and normal reconnect; metadata/catalog + local record match; ordinary typing and SpaceFn confirmed by user |

RT HFB SHA-256: `a0635d6939d309a9b448942f4e80285cce7471591c344ef2830951af50d8a455`.

HOLD HFB SHA-256: `07553a08906d8bfe8153601fcca1a7d61189cf5c5a71720f93ff13954ac33ce5`.

Catalog: `development-20261017-3`, merged with local build records during inspection.
The reported build ID is connected to a recipe. Settings and the full flash image
were not read back; estimated distances were not physically calibrated.

Official HHKB app compatibility was checked for earlier BA90567B/ECC9B8A2
candidates, but was not reported for these two GUI-generated builds. Other
devices/configurations, default RT 81B8EDEB, interrupted-update recovery and
clean-PC installation remain separate validation targets. These trials do not
establish all configurations as safe or promote a public release.

SpaceFn fast-typing space ordering remains a documented behavior limitation.
Creation-time manifests and immutable catalog snapshots are preserved; follow-up
hardware evidence does not rewrite them. Current user-reported installation is
HOLD A96B4BA0. RT and HOLD are alternative firmware builds.
