# {{ project_name }}

{% if project_description %}
> **Project Description:** {{ project_description }}
{% endif %}

**Author:** {{ author | default('Scribe') }}
**Version:** {{ version | default('1.0.0') }}
**Created:** {{ timestamp }}
**Organization:** {{ organization | default('Claude Code') }}

---

## Quick Links

{% if links %}
{% for link_name, link_url in links.items() %}
- [{{ link_name | title }}]({{ link_url }})
{% endfor %}
{% endif %}

---

## Project Overview

{% if features %}
### Features
{% for feature in features %}
- {{ feature }}
{% endfor %}
{% endif %}

{% if project_slug %}
**Project Slug:** `{{ project_slug }}`
**Timezone:** {{ standards.timezone | default('UTC') }}
**Encoding:** {{ standards.encoding | default('UTF-8') }}
**Line Endings:** {{ standards.line_endings | default('LF') }}
{% endif %}

---

*This project uses the Scribe MCP system for documentation and progress tracking.*