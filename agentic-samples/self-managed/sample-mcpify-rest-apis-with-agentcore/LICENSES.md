# Open Source License Report

**Project:** demo-retail  
**Generated:** 2025-11-14  
**Dependencies Source:** app/requirements.txt

## Direct Dependencies

| Package | Version | License | Status |
|---------|---------|---------|--------|
| Flask | 2.3.3 | BSD-3-Clause | ✅ APPROVED |
| gunicorn | 23.0.0 | MIT | ✅ APPROVED |
| boto3 | 1.34.0 | Apache-2.0 | ✅ APPROVED |

## License Details

### BSD-3-Clause (Flask)
- **Type:** Permissive
- **Commercial Use:** ✅ Allowed
- **Modification:** ✅ Allowed
- **Distribution:** ✅ Allowed
- **Patent Grant:** ❌ No
- **Trademark Use:** ❌ No
- **Source:** https://github.com/pallets/flask/blob/main/LICENSE.txt

### MIT License (gunicorn)
- **Type:** Permissive
- **Commercial Use:** ✅ Allowed
- **Modification:** ✅ Allowed
- **Distribution:** ✅ Allowed
- **Patent Grant:** ❌ No
- **Source:** https://github.com/benoitc/gunicorn/blob/master/LICENSE

### Apache-2.0 (boto3)
- **Type:** Permissive
- **Commercial Use:** ✅ Allowed
- **Modification:** ✅ Allowed
- **Distribution:** ✅ Allowed
- **Patent Grant:** ✅ Yes
- **Trademark Use:** ❌ No
- **Source:** https://github.com/boto/boto3/blob/develop/LICENSE

## Compliance Summary

✅ **ALL LICENSES APPROVED**

All dependencies use permissive open source licenses that are commonly approved for customer engagements:

- **BSD-3-Clause**: Standard permissive license, widely accepted
- **MIT**: Most permissive license, universally accepted
- **Apache-2.0**: Enterprise-friendly with patent protection

### Key Points

1. **No Copyleft Licenses**: None of the dependencies use GPL, AGPL, or other copyleft licenses
2. **Commercial Use**: All licenses permit commercial use
3. **Modification**: All licenses allow modification and derivative works
4. **Distribution**: All licenses allow redistribution
5. **Patent Protection**: Apache-2.0 provides explicit patent grant

## Transitive Dependencies

Note: This report covers direct dependencies only. For a complete analysis including transitive dependencies, run:

```bash
pip install pip-licenses
pip-licenses --format=markdown --with-urls
```

## Recommendations

✅ **No action required** - All licenses are approved for customer engagements.

For ongoing compliance:
1. Review licenses when adding new dependencies
2. Document any license changes in dependency updates
3. Maintain this report with each major release
