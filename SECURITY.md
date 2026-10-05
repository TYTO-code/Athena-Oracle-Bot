# Security Policy

## Reporting a vulnerability

**Please do not open a public issue, pull request or discussion for a security
problem.** Report it privately instead:

1. Use GitHub's **private vulnerability reporting**: on this repository, go to
   *Security → Report a vulnerability*.
2. Include what you found, how to reproduce it, and the impact you believe it has.

We will acknowledge your report, keep you informed, and credit you if you wish
once the issue is fixed. Please give us a reasonable time to fix it before any
public disclosure. Good-faith research on your own copy of the code is welcome
(see Section 4 of the [LICENSE](LICENSE)); do not access systems, accounts, data
or infrastructure that you do not own, and do not test against our production
Discord server, databases or APIs.

## If you find a secret or personal data in this repository

Do not use it. Report it through the channel above so that we can revoke and
remove it. Never publish it in an issue.

## Scope

In scope: the code in this repository (the Atena / Oráculo bot and its API).
Out of scope: social engineering, denial of service by volume, and vulnerabilities
in third-party dependencies that are already publicly known (report those
upstream).

## Security model in short

- The bot is **read-only** towards the TYTO.club platform and only answers
  members with an active registration (see `docs/04-arquitetura/adr-002-bot-somente-leitura.md`).
- Webhooks are verified with HMAC-SHA256 over the raw body, in constant time.
- No credentials belong in the repository: configuration comes from environment
  variables (`.env.example` lists the names, never values).
- The Firebase service account used by the bot must be **read-only**
  (`roles/datastore.viewer`).
