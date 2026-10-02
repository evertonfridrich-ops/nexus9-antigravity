# Security Policy

## Supported Versions

| Version | Supported          |
| ------- | ------------------ |
| 0.3.x   | :white_check_mark: |
| < 0.3.0 | :x:                |

## Reporting a Vulnerability

If you discover a security vulnerability or security defect in **NEXUS9**, please report it privately:

* **Contact:** Everton Fridrich (`evertonfridrich@gmail.com`)
* **Subject:** `[SECURITY] NEXUS9 Vulnerability Report`

Please include:
1. Detailed description of the vulnerability.
2. Steps or proof-of-concept (PoC) to reproduce the issue.
3. Potential impact and attack vectors.

### Response Commitment
* **Acknowledgement:** Within 48 hours.
* **Assessment & Fix:** Security patches will be prioritized and released as immediate patch releases.
* **Coordinated Disclosure:** We kindly ask reporters to adhere to coordinated disclosure principles and avoid publishing details publicly before a fix is released.

## Security Architecture & Threat Model

NEXUS9 runs as a local stdio MCP server on the developer's machine. For detailed technical discussion of path validation, credential redaction, TOCTOU boundaries, and operational limits, see [docs/SECURITY.md](docs/SECURITY.md).
