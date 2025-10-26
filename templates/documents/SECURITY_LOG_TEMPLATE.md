# 🔒 Security Log — {{PROJECT_NAME}}
**Maintained By:** {{AUTHOR}}
**Timezone:** UTC

> This log tracks security-related events, vulnerabilities, and security decisions. Use via Scribe MCP tool with `log_type="security"` or `--log security`.

{{#IS_ROTATION}}
---

## 🔄 Log Rotation Information
**Rotation ID:** {{ROTATION_ID}}
**Rotation Timestamp:** {{ROTATION_TIMESTAMP_UTC}}
**Current Sequence:** {{CURRENT_SEQUENCE}}
**Total Rotations:** {{TOTAL_ROTATIONS}}

{{#PREVIOUS_LOG_PATH}}
### Previous Log Reference
- **Path:** {{PREVIOUS_LOG_PATH}}
- **Hash:** {{PREVIOUS_LOG_HASH}}
- **Entries:** {{PREVIOUS_LOG_ENTRIES}}
{{/PREVIOUS_LOG_PATH}}
{{/IS_ROTATION}}

---

## Entry Format
```
[EMOJI] [YYYY-MM-DD HH:MM:SS UTC] [Agent: <name>] [Project: {{PROJECT_NAME}}] Message text | severity=<severity>; area=<area>; impact=<impact>; [additional metadata]
```

**Required Metadata Fields:**
- `severity`: Security severity level (critical/high/medium/low/ informational)
- `area`: Security area affected (authentication/data_storage/network/code_injection/infrastructure/configuration)
- `impact`: Business impact level (critical/high/medium/low/minimal)

**Optional Metadata Fields:**
- `cve_id`: CVE identifier if applicable
- `cvss_score`: CVSS scoring (0-10)
- `component`: Specific component or module affected
- `mitigation_status`: Status of mitigation (open/in_progress/mitigated/accepted_risk)
- `mitigation_date`: Date when mitigation was implemented
- `reviewer`: Security reviewer name
- `test_coverage`: Test coverage status (covered/partial/uncovered)
- `compliance_framework`: Relevant compliance frameworks (SOC2/GDPR/HIPAA/PCI_DSS)
- `remediation_priority`: Priority for remediation (P0/P1/P2/P3)

---

## Severity Classification Guide
- **Critical**: Immediate threat to production data/systems, requires immediate action
- **High**: Significant security risk, should be addressed within 24 hours
- **Medium**: Moderate security risk, should be addressed within 1 week
- **Low**: Minor security issue, should be addressed in next release cycle
- **Informational**: Security best practices, observations, or improvements

---

## Security Areas
- **Authentication**: Login, authorization, identity management
- **Data Storage**: Encryption, database security, data handling
- **Network**: API security, network segmentation, firewall rules
- **Code Injection**: XSS, SQL injection, command injection vulnerabilities
- **Infrastructure**: Server security, container security, secrets management
- **Configuration**: Security settings, permissions, access controls

---

## Entry will populate below