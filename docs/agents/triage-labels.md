# Triage labels

This repo uses the default triage label vocabulary — each canonical role is its own label string.

| Role | Label |
|------|-------|
| Needs triage | `needs-triage` |
| Needs info | `needs-info` |
| Ready for agent | `ready-for-agent` |
| Ready for human | `ready-for-human` |
| Won't fix | `wontfix` |

The `/triage` skill reads and writes these labels. If your issue tracker already uses different names, edit this file to map them — each line is `role: label-string`, and the skill reads them as-is.
