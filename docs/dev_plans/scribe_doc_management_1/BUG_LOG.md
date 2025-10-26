# 🐞 Bug Log — scribe_doc_management_1
**Maintained By:** Scribe
**Timezone:** UTC

> This log tracks bug discoveries, investigations, and resolutions. Use via Scribe MCP tool with `log_type="bugs"` or `--log bugs`.

TBD
---

## 🔄 Log Rotation Information
**Rotation ID:** TBD
**Rotation Timestamp:** TBD
**Current Sequence:** TBD
**Total Rotations:** TBD

TBD
### Previous Log Reference
- **Path:** TBD
- **Hash:** TBD
- **Entries:** TBD
TBD
TBD

---

## Entry Format
```
[EMOJI] [YYYY-MM-DD HH:MM:SS UTC] [Agent: <name>] [Project: scribe_doc_management_1] Message text | severity=<severity>; component=<component>; status=<status>; [additional metadata]
```

**Required Metadata Fields:**
- `severity`: Bug severity (critical/high/medium/low/minimal)
- `component`: Component or module where bug was found
- `status`: Bug status (open/investigating/in_progress/fixed/verified/closed/wont_fix)

**Optional Metadata Fields:**
- `bug_id`: Unique bug identifier (ticket number, JIRA ID, etc.)
- `environment`: Where bug was found (production/staging/development/local)
- `reproduction_steps`: Brief description of how to reproduce
- `test_case`: Test case ID or name that should catch this bug
- `fix_commit`: Commit hash where bug was fixed
- `reviewer`: Code reviewer who approved the fix
- `confidence`: Confidence in the root cause analysis (0-1)
- `impact`: Business impact level (critical/high/medium/low/minimal)
- `customer_impacted`: Whether customers were affected (true/false)
- `regression`: Whether this is a regression from previous version (true/false)
- `estimated_effort`: Time/complexity estimate to fix (XS/S/M/L/XL)
- `related_issues`: Comma-separated list of related issue IDs

---

## Severity Classification Guide
- **Critical**: System down, data loss, security vulnerability, customer production issues
- **High**: Major feature broken, significant customer impact, workarounds limited
- **Medium**: Feature partially broken, minor customer impact, workarounds available
- **Low**: Minor UI issues, edge cases, documentation errors
- **Minimal**: Typos, cosmetic issues, non-functional improvements

---

## Component Categories
- **Backend**: Server-side code, APIs, databases, business logic
- **Frontend**: UI components, user interface, client-side logic
- **Infrastructure**: Deployment, CI/CD, monitoring, configurations
- **Tests**: Unit tests, integration tests, test infrastructure
- **Documentation**: READMEs, API docs, user guides
- **Performance**: Performance issues, bottlenecks, optimizations
- **Security**: Security-related bugs and vulnerabilities
- **Data**: Data migration, seeding, validation issues

---

## Status Flow Guide
1. **open** → Initial discovery and logging
2. **investigating** → Root cause analysis in progress
3. **in_progress** → Fix being developed
4. **fixed** → Fix implemented, ready for testing
5. **verified** → Fix tested and confirmed working
6. **closed** → Issue resolved and documented
7. **wont_fix** → Issue intentionally not addressed (with justification)

---

## Entry will populate below