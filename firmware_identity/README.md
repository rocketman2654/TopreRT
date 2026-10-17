# Development metadata reader

This standalone app package carries a copy of the reviewed HHKB reader, payload
parser and build catalog. Runtime imports do not depend on workspace research,
local firmware binaries or an installed compiler. SOURCE_MANIFEST.json records
the exact original sources and bundled file hashes. Original firmware/research
sources and candidate IDs remain unchanged.

Package changes are limited to local imports, the isolated worker's app path and
extraction of the Windows constructor/strict UTF-16 decoder. The unused product
string query was omitted. Metadata still requests only index7/language0409 once,
requires the complete110-byte result and validates envelope/CRC/product/catalog.
The parent bounds the worker and never retries a failed query.

The catalog contains Development build claims, including hardware-tried RT
BA90567B and HOLD ECC9B8A2. A catalog match does not authenticate a whole firmware
image, read settings back, or establish USB device identity. Older rc3/rc4 builds
have no metadata and cannot acquire an exact release label through this catalog.

The GUI queries metadata only when Inspect firmware is selected. Detect performs
USB enumeration only. Development generation now layers the reviewed template
over existing RT/HOLD builders and revalidates exact output. See
../docs/METADATA_GENERATION_DEVELOPMENT.md. Versioned catalog snapshots are under
catalogs/; custom records stay in output/identity. Recipe settings are not live
settings readback. GUI-generated RT B33E6ADF and SpaceFn A96B4BA0 have user-confirmed
hardware coverage described in ../docs/HARDWARE_IDENTIFICATION_20261018.md.
Default RT 81B8EDEB and other configurations require separate hardware trials.
