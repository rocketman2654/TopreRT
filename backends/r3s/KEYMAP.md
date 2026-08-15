# REALFORCE R3S key map — observed subset

This map contains only keys that were directly observed with the read-only C5 mapper.
Unmapped keys are intentionally left unknown rather than inferred.

| Physical key | Internal index |
|---|---:|
| W | 17 |
| E | 18 |
| R | 19 |
| A | 30 |
| S | 31 |
| D | 32 |
| Space | 60 |

Current known checks:

- R -> 19
- Space -> 60

To extend the map:

```powershell
py .\r3sb_c5_key_mapper_v1_2.py
```

The mapper is read-only and writes only local JSON/CSV mapping files.