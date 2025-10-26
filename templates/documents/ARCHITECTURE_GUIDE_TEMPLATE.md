# 🏗️ Architecture Guide — {{PROJECT_NAME}}
**Author:** {{AUTHOR}}
**Version:** Draft v0.1
**Last Updated:** {{DATE_UTC}}

> TODO: Replace every placeholder and instructional block with project-specific detail. Keep this document in sync with reality—update it the moment architecture or directory structure changes.

---

## 1. Problem Statement
<!-- ID: problem_statement -->
- **Context:** Why are we building this? Who benefits?
- **Goals:** Bullet the concrete outcomes we must achieve.
- **Non-Goals:** Explicitly list what is out of scope.
- **Success Metrics:** How will we measure impact?

---

## 2. Requirements & Constraints
<!-- ID: requirements_constraints -->
- **Functional Requirements:** Capabilities the system must provide.
- **Non-Functional:** Performance, reliability, security, compliance.
- **Assumptions:** Dependencies and environmental expectations.
- **Risks & Mitigations:** Known risks with mitigation strategies.

---

## 3. Architecture Overview
<!-- ID: architecture_overview -->
- **Solution Summary:** Two to three paragraphs summarising the design.
- **Component Breakdown:** Table or bullets describing each major component, its responsibilities, and interactions.
- **Data Flow:** Narrative + link/inline diagram showing how data moves through the system.
- **External Integrations:** APIs, queues, services, or third-party dependencies.

---

## 4. Detailed Design
<!-- ID: detailed_design -->
For each subsystem or component:
1. **Purpose** – why it exists.
2. **Interfaces** – inputs, outputs, data contracts, schemas.
3. **Implementation Notes** – libraries, algorithms, patterns.
4. **Error Handling** – failure modes and recovery strategy.

Repeat until every meaningful slice of the system is documented.

---

## 5. Directory Structure (Keep Updated)
<!-- ID: directory_structure -->
```
{{PROJECT_ROOT}}/
  # TODO: replace with the real directory tree for {{PROJECT_NAME}}
```

> Agents rely on this tree for orientation. Update whenever files are added, removed, or reorganised.

---

## 6. Data & Storage
<!-- ID: data_storage -->
- **Datastores:** Tables/collections involved, with schema snapshots.
- **Indexes & Performance:** Indexing strategy, retention, archival plans.
- **Migrations:** Steps, ordering, rollback plan.

---

## 7. Testing & Validation Strategy
<!-- ID: testing_strategy -->
- **Unit Tests:** Scope and coverage targets.
- **Integration Tests:** Required environments, fixtures, and data sets.
- **Manual QA:** Exploratory plans or acceptance walkthroughs.
- **Observability:** Logging, metrics, tracing, alerting expectations.

---

## 8. Deployment & Operations
<!-- ID: deployment_operations -->
- **Environments:** Dev/staging/prod differences.
- **Release Process:** Automation, approvals, rollback.
- **Configuration Management:** Secrets, feature flags, runtime toggles.
- **Maintenance & Ownership:** On-call, SLOs, future work.

---

## 9. Open Questions & Follow-Ups
<!-- ID: open_questions -->
| Item | Owner | Status | Notes |
| ---- | ----- | ------ | ----- |
| {{FILL_ME}} | {{FILL_ME}} | {{TODO}} | Capture decisions, blockers, or research tasks. |

Close each question once answered and reference the relevant section above.

---

## 10. References & Appendix
<!-- ID: references_appendix -->
- Link to diagrams, ADRs, research notes, or external specs.
- Include raw data, calculations, or supporting materials.

